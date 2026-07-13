"""
Auth Router — регистрация, вход, профиль, OAuth
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from datetime import datetime
import secrets
import httpx

import database
import models
import schemas
import auth_service
import oauth_service
from oauth_state_store import get_state_store
from rate_limiter import limiter, AUTH_LIMIT, REGISTER_LIMIT, EXPORT_LIMIT
from utils.datetime_utils import utc_now_naive
from utils.log_redaction import mask_email
from logger import get_logger

log = get_logger("auth")

router = APIRouter(prefix="/auth", tags=["auth"])

# Хранилище state для OAuth с поддержкой Redis
oauth_store = get_state_store()


# ==================== AUTH ENDPOINTS ====================

def _neutral_register_response(password: str, notify_email: str) -> JSONResponse:
    """SEC (S4-11): нейтральный ответ на дубль/гонку, неотличимый от happy-path.

    Уравниваем не только код/тело, но и ТАЙМИНГ: happy-path платит bcrypt-цену
    в create_user → get_password_hash (rounds=BCRYPT_ROUNDS). Здесь прогоняем
    дамми-хеш той же стоимости и отбрасываем — иначе латентность выдаёт, что
    email существует (образец: auth_service.authenticate_user дамми-check).
    Best-effort уведомляем реального владельца письмом.
    """
    auth_service.get_password_hash(password)
    log.info("register: duplicate email attempt email=%s", mask_email(notify_email))
    try:
        from services.email_service import send_duplicate_registration_notice
        send_duplicate_registration_notice(notify_email)
    except Exception:
        log.exception("register: duplicate-notice email send failed (non-blocking)")
    return JSONResponse(
        status_code=202,
        content={"message": "Если email свободен — аккаунт создан. Проверьте почту."},
    )


@router.post("/register", response_model=schemas.AuthSuccess)
@limiter.limit(REGISTER_LIMIT)
def register(request: Request, response: Response, user_data: schemas.UserCreate, db: Session = Depends(database.get_db)):
    """
    Регистрация нового пользователя.
    Возвращает пару JWT токенов (access + refresh) для авторизации.
    Rate limit: 3 запроса в минуту.

    152-ФЗ: требуется явное согласие на обработку ПД (поле pd_consent=true).
    Согласие записывается в `pd_consents` с IP и User-Agent — это
    доказательная база для проверок РКН.
    """
    # 152-ФЗ ст. 9: согласие должно быть явным. Pydantic уже проверил тип bool,
    # но значение может быть False — это нарушение, отклоняем.
    if not user_data.pd_consent:
        raise HTTPException(
            status_code=400,
            detail="Требуется согласие на обработку персональных данных (152-ФЗ)"
        )

    existing_user = auth_service.get_user_by_email(db, user_data.email)
    if existing_user:
        return _neutral_register_response(user_data.password, existing_user.email)

    try:
        user = auth_service.create_user(db, user_data)
    except IntegrityError:
        # SEC (S4-11): конкурентная регистрация нового email — второй commit
        # ловит UNIQUE(users.email). Откатываем и отвечаем тем же нейтральным
        # 202, что и для дубля, чтобы гонка не приоткрывала enumeration через 500.
        db.rollback()
        return _neutral_register_response(user_data.password, user_data.email)

    # Записываем согласие в журнал — версионируем по политике конфиденциальности.
    # При смене текста политики версия инкрементируется, и юзер должен подтвердить заново.
    consent = models.PdConsent(
        user_id=user.id,
        consent_text_version="v1",
        accepted_at=utc_now_naive(),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(consent)

    # PR 26 Phase 3: выпускаем email verification token + шлём письмо.
    # Юзер может пользоваться сервисом сразу (email_verified=False, но JWT
    # выдан), но некоторые фичи могут потребовать verified email — это
    # решается на frontend через `user.email_verified` флаг.
    verification_token = secrets.token_urlsafe(32)
    user.email_verification_token = verification_token
    user.email_verification_sent_at = utc_now_naive()
    db.commit()

    try:
        from services.email_service import send_email_verification
        from config import settings as _settings
        verify_url = f"{_settings.PUBLIC_URL}/auth/verify-email?token={verification_token}"
        send_email_verification(user.email, verify_url, user_name=getattr(user, "name", None))
    except Exception:
        log.exception("register: email verification send failed (non-blocking)")

    # Создаём пару токенов
    access_token, refresh_token = auth_service.create_token_pair(user.id, user.email)
    auth_service.set_auth_cookies(response, request, access_token, refresh_token)

    log.info("✅ Зарегистрирован новый пользователь: user_id=%s (consent v1)", user.id)

    # SEC-08: токены отдаём только в httpOnly cookies, не в теле ответа.
    return {
        "token_type": "bearer",
        "expires_in": auth_service.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "authenticated": True,
    }


@router.post("/login", response_model=schemas.AuthSuccess)
@limiter.limit(AUTH_LIMIT)
def login(request: Request, response: Response, user_data: schemas.UserLogin, db: Session = Depends(database.get_db)):
    """
    Вход в систему.
    Возвращает пару JWT токенов (access + refresh) для авторизации.
    Rate limit: 5 запросов в минуту (защита от brute-force).
    """
    user = auth_service.authenticate_user(db, user_data.email, user_data.password)
    
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Неверный email или пароль"
        )
    
    if user.is_active != 1:
        raise HTTPException(
            status_code=403,
            detail="Аккаунт деактивирован"
        )

    # S1-06: если у юзера включён TOTP, финальную пару токенов не выдаём
    # до проверки 6-значного кода — иначе 2FA была бы фиктивной защитой.
    #
    # S1-06c: detail — dict с машиночитаемым totp_required=true (паттерн уже
    # используется в кодовой базе, см. pro_required в subscription_service.py).
    # Пароль на этом шаге уже подтверждён authenticate_user() выше — раскрытие
    # факта "у юзера включена 2FA" не даёт атакующему ничего сверх того, что
    # он и так знает (пароль верный, но недостаточен). Без dict-сигнала фронт
    # вынужден был бы matchить строку detail по языку — brittle и небезопасно
    # при локализации.
    if user.totp_enabled:
        from services.totp_service import verify_code_for_user
        if not user_data.totp_code or not verify_code_for_user(user, user_data.totp_code, db=db):
            raise HTTPException(
                status_code=401,
                detail={
                    "message": "Требуется код двухфакторной аутентификации",
                    "totp_required": True,
                },
            )
        # S4-10: персистим totp_last_used_step ДО выдачи токенов — иначе
        # replay-guard бесполезен (шаг не сохранится между запросами).
        db.commit()

    # Создаём пару токенов
    access_token, refresh_token = auth_service.create_token_pair(user.id, user.email)
    auth_service.set_auth_cookies(response, request, access_token, refresh_token)

    log.info("🔑 Вход пользователя: user_id=%s", user.id)

    # SEC-08: токены отдаём только в httpOnly cookies, не в теле ответа.
    return {
        "token_type": "bearer",
        "expires_in": auth_service.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "authenticated": True,
    }


@router.post("/refresh", response_model=schemas.AuthSuccess)
@limiter.limit(AUTH_LIMIT)
def refresh_tokens(
    request: Request,
    response: Response,
    token_request: schemas.TokenRefreshRequest | None = None,
    db: Session = Depends(database.get_db)
):
    """
    Обновление токенов по refresh токену.
    
    Используйте этот endpoint когда access токен истёк.
    Refresh токен должен быть валиден.
    """
    refresh_token = auth_service.get_refresh_token_from_request(
        request,
        token_request.refresh_token if token_request else None,
    )

    if not refresh_token:
        raise HTTPException(
            status_code=401,
            detail="Refresh токен отсутствует"
        )

    result = auth_service.refresh_tokens(refresh_token, db)
    
    if result is None:
        raise HTTPException(
            status_code=401,
            detail="Refresh токен недействителен или истёк"
        )
    
    access_token, refresh_token = result
    auth_service.set_auth_cookies(response, request, access_token, refresh_token)

    log.debug("🔄 Токены обновлены")

    # SEC-08: токены отдаём только в httpOnly cookies, не в теле ответа.
    return {
        "token_type": "bearer",
        "expires_in": auth_service.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "authenticated": True,
    }


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(database.get_db),
):
    """Завершить сессию и очистить auth cookies.

    PR 26: дополнительно отзываем JWT (access + refresh) через jti →
    revoked_tokens. Без этого украденный токен оставался валидным до
    естественного expiry даже после logout.
    """
    # PR 26: пробуем извлечь токен из Authorization header И из cookie.
    # `get_access_token_from_request` принимает credentials=None и берёт
    # только из cookie; для Bearer-flow читаем header напрямую.
    try:
        access_token = request.cookies.get(auth_service.ACCESS_TOKEN_COOKIE_NAME)
        if not access_token:
            authz = request.headers.get("authorization", "")
            if authz.lower().startswith("bearer "):
                access_token = authz[7:].strip()
        if access_token:
            td = auth_service.decode_access_token(access_token)
            if td and td.jti:
                auth_service.revoke_token(
                    db,
                    jti=td.jti,
                    user_id=td.user_id,
                    exp_ts=td.exp_ts,
                    reason="logout",
                )
    except Exception:
        pass
    try:
        refresh_token = request.cookies.get("refresh_token")
        if refresh_token:
            td = auth_service.decode_refresh_token(refresh_token)
            if td and td.jti:
                auth_service.revoke_token(
                    db,
                    jti=td.jti,
                    user_id=td.user_id,
                    exp_ts=td.exp_ts,
                    reason="logout",
                )
    except Exception:
        pass

    auth_service.clear_auth_cookies(response, request)
    response.status_code = 204
    return response


@router.get("/me", response_model=schemas.UserResponse)
def get_current_user_info(
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """
    Получить информацию о текущем авторизованном пользователе.
    Требует Bearer токен в заголовке Authorization.
    """
    return current_user


@router.get("/subscription")
def get_current_user_subscription(
    current_user: models.User = Depends(auth_service.get_current_user),
    db: Session = Depends(database.get_db)
):
    """
    Получить информацию о подписке текущего пользователя.
    """
    return auth_service.get_user_subscription(db, current_user)


@router.put("/me", response_model=schemas.UserResponse)
def update_current_user(
    user_data: schemas.UserUpdate,
    current_user: models.User = Depends(auth_service.get_current_user),
    db: Session = Depends(database.get_db)
):
    """
    Обновить профиль текущего пользователя.
    """
    updated_user = auth_service.update_user(db, current_user, user_data)
    log.info("✏️ Обновлён профиль пользователя: user_id=%s", updated_user.id)
    return updated_user


@router.delete("/me", status_code=202)
def delete_account(
    request: Request,
    response: Response,
    payload: schemas.DeleteAccountRequest,
    current_user: models.User = Depends(auth_service.get_current_user),
    db: Session = Depends(database.get_db)
):
    """
    Запросить удаление аккаунта (152-ФЗ ст. 14).

    Реализован двухфазный подход:
    1. Этот endpoint ставит deletion_requested_at = now() (soft delete + 30 дней).
    2. Финализация — отдельный фоновый процесс через 30 дней (services/pd_deletion.py).

    OAuth-юзеры могут не иметь пароля — для них дополнительная проверка не делается,
    но лимит запросов ограничит злоупотребление.

    Возвращает 202 Accepted — операция принята, но финализируется через 30 дней.
    """
    # S4-16: под impersonation-токеном удаление аккаунта запрещено (non-repudiation).
    # Follow-up: применить тот же гвард к /auth/change-password и платёжным операциям.
    auth_service.assert_not_impersonation(request)

    # OAuth-аккаунты могут не иметь пароля — пропускаем проверку, иначе требуем
    if current_user.hashed_password:
        if not auth_service.verify_password(payload.password, current_user.hashed_password):
            raise HTTPException(status_code=400, detail="Неверный пароль")

    if current_user.deletion_requested_at is not None:
        raise HTTPException(status_code=409, detail="Запрос на удаление уже подан")

    # Импортируем здесь, чтобы избежать циклов на модульном уровне
    from services import pd_deletion

    pd_deletion.request_account_deletion(
        db,
        user=current_user,
        reason=payload.reason,
        ip_address=request.client.host if request.client else None,
    )

    # Сбрасываем cookies — юзер фактически разлогинен
    auth_service.clear_auth_cookies(response, request)

    log.info(f"🗑 Запрос на удаление аккаунта: user_id={current_user.id}")

    return {
        "status": "deletion_requested",
        "grace_period_days": 30,
        "message": "Аккаунт будет удалён через 30 дней. До этого момента вы можете восстановить его."
    }


@router.get("/me/export", response_model=schemas.UserDataExport)
@limiter.limit(EXPORT_LIMIT)
def export_my_data(
    request: Request,
    current_user: models.User = Depends(auth_service.get_current_user),
    db: Session = Depends(database.get_db),
):
    """
    Экспорт всех персональных данных пользователя (152-ФЗ ст. 14 — право доступа).

    Возвращает JSON со всеми данными: User, Accounts, Trades, Payments,
    pd_consents и т.д. БЕЗ хешированного пароля и брокерских токенов.

    Rate-limit 5/hour — операция тяжёлая (читает несколько таблиц), смысла
    спамить нет.
    """
    # S4-16: экспорт раскрывает полный PII (152-ФЗ) — под impersonation-токеном
    # запрещён (non-repudiation), выше по риску, чем удаление аккаунта.
    auth_service.assert_not_impersonation(request)

    from services import pd_export

    request_id = request.headers.get("x-request-id")
    data = pd_export.build_user_export(db, current_user, request_id=request_id)

    log.info(
        f"📦 PD export user_id={current_user.id} "
        f"trades={data['counts']['trades']} accounts={data['counts']['accounts']}"
    )

    return data


@router.post("/change-password")
def change_password(
    request: Request,
    password_data: schemas.ChangePasswordRequest,
    current_user: models.User = Depends(auth_service.get_current_user),
    db: Session = Depends(database.get_db)
):
    """
    Изменить пароль текущего пользователя.
    """
    # S4-16: смена пароля под impersonation-токеном запрещена (non-repudiation).
    auth_service.assert_not_impersonation(request)

    if not current_user.hashed_password:
        raise HTTPException(
            status_code=400,
            detail="Для OAuth-аккаунта смена пароля недоступна"
        )

    if not auth_service.verify_password(password_data.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=400,
            detail="Неверный текущий пароль"
        )
    
    if password_data.old_password == password_data.new_password:
        raise HTTPException(
            status_code=400,
            detail="Новый пароль должен отличаться от текущего"
        )

    if len(password_data.new_password) < 12:
        raise HTTPException(
            status_code=400,
            detail="Новый пароль должен быть минимум 12 символов"
        )
    
    current_user.hashed_password = auth_service.get_password_hash(password_data.new_password)
    # API-07: смена пароля инвалидирует все активные JWT (decision (d) = yes).
    current_user.tokens_valid_after = utc_now_naive()
    db.commit()

    log.info("🔒 Пароль изменён для пользователя: user_id=%s", current_user.id)

    return {"message": "Пароль успешно изменён"}


# ==================== EMAIL VERIFICATION (PR 26 Phase 3) ====================

@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(database.get_db)):
    """PR 26 Phase 3: подтверждение email по magic-link.

    GET вместо POST потому что юзер кликает по ссылке в письме — браузер
    делает GET. Token = 32-byte URL-safe, expires через 24h.
    """
    from datetime import timedelta

    user = db.query(models.User).filter(
        models.User.email_verification_token == token
    ).first()

    if user is None:
        raise HTTPException(status_code=404, detail="Ссылка недействительна")

    if user.email_verification_sent_at:
        age = utc_now_naive() - user.email_verification_sent_at
        if age > timedelta(hours=24):
            raise HTTPException(status_code=400, detail="Ссылка истекла. Запросите новую.")

    user.email_verified = True
    user.email_verification_token = None
    db.commit()

    log.info("email verified: user_id=%s", user.id)
    return {"ok": True, "message": "Email подтверждён. Можете войти."}


@router.post("/resend-verification", status_code=202)
@limiter.limit(AUTH_LIMIT)
def resend_verification(
    request: Request,
    current_user: models.User = Depends(auth_service.get_current_user),
    db: Session = Depends(database.get_db),
):
    """PR 26 Phase 3: перевыпустить ссылку подтверждения. Rate-limited."""
    import secrets as _secrets
    from services.email_service import send_email_verification
    from config import settings as _settings

    if current_user.email_verified:
        raise HTTPException(status_code=400, detail="Email уже подтверждён")

    token = _secrets.token_urlsafe(32)
    current_user.email_verification_token = token
    current_user.email_verification_sent_at = utc_now_naive()
    db.commit()

    verify_url = f"{_settings.PUBLIC_URL}/auth/verify-email?token={token}"
    try:
        send_email_verification(current_user.email, verify_url, user_name=getattr(current_user, "name", None))
    except Exception:
        log.exception("resend verification email failed")

    return {"message": "Письмо отправлено."}


# ==================== TOTP 2FA (PR 26 Phase 2) ====================

@router.post("/2fa/enable", response_model=schemas.TotpEnableResponse)
def totp_enable(
    current_user: models.User = Depends(auth_service.get_current_user),
    db: Session = Depends(database.get_db),
):
    """PR 26 Phase 2: подключить TOTP 2FA.

    Возвращает `secret` + `provisioning_uri` (для QR-кода). Не активирует
    до verify — юзер должен подтвердить что секрет успешно добавлен в
    authenticator app.
    """
    from services.totp_service import generate_secret, provisioning_uri

    if current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA уже включён")

    new_secret = generate_secret()
    current_user.totp_secret = new_secret
    # totp_enabled остаётся False до verify
    db.commit()

    return schemas.TotpEnableResponse(
        secret=new_secret,
        provisioning_uri=provisioning_uri(new_secret, current_user.email),
    )


@router.post("/2fa/verify", status_code=200)
def totp_verify(
    payload: schemas.TotpVerifyRequest,
    current_user: models.User = Depends(auth_service.get_current_user),
    db: Session = Depends(database.get_db),
):
    """PR 26 Phase 2: подтвердить 2FA активацию вводом первого кода."""
    from services.totp_service import verify_code_for_user

    if not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="Сначала вызовите /2fa/enable")

    if not verify_code_for_user(current_user, payload.code, db=db):
        raise HTTPException(status_code=400, detail="Неверный код. Попробуйте ещё раз.")

    current_user.totp_enabled = True
    db.commit()
    log.info("2FA activated: user_id=%s", current_user.id)
    return {"ok": True}


@router.post("/2fa/disable", status_code=200)
def totp_disable(
    payload: schemas.TotpVerifyRequest,
    current_user: models.User = Depends(auth_service.get_current_user),
    db: Session = Depends(database.get_db),
):
    """PR 26 Phase 2: отключить 2FA. Требует валидный TOTP код (чтобы
    атакующий с угнанным cookie не отключил защиту)."""
    from services.totp_service import verify_code_for_user

    if not current_user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA не активирована")

    if not verify_code_for_user(current_user, payload.code, db=db):
        raise HTTPException(status_code=400, detail="Неверный код")

    current_user.totp_enabled = False
    current_user.totp_secret = None
    db.commit()
    log.info("2FA deactivated: user_id=%s", current_user.id)
    return {"ok": True}


# ==================== PASSWORD RESET (PR 26) ====================

@router.post("/password-reset/request", status_code=202)
@limiter.limit(AUTH_LIMIT)
def password_reset_request(
    request: Request,
    payload: schemas.PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
):
    """PR 26: запросить ссылку для сброса пароля.

    Принципы:
    - Всегда возвращаем 202 (даже если email не найден) — защита от
      enumeration. Атакующий не может узнать, какие email зарегистрированы.
    - One-time token (32-byte URL-safe), expires в 1 час.
    - Существующие неиспользованные токены этого юзера инвалидируем.
    - Email отправляем best-effort (не падаем если SMTP не настроен).
    """
    from datetime import timedelta
    from services.email_service import send_password_reset_email

    email = payload.email.strip().lower()
    user = db.query(models.User).filter(models.User.email == email).first()

    # Всегда отвечаем 202 — независимо от того, найден ли user. Это защита
    # от user enumeration через timing.
    response_payload = {"message": "Если такой email зарегистрирован, мы выслали ссылку."}

    if user is None or user.is_active != 1:
        log.info("password_reset_request: ignored email=%s (user not found or inactive)", mask_email(email))
        return response_payload

    # OAuth-only users без пароля не могут его сбрасывать.
    if not user.hashed_password:
        log.info("password_reset_request: ignored email=%s (OAuth-only)", mask_email(email))
        return response_payload

    # Инвалидируем все pending токены этого юзера.
    db.query(models.PasswordResetTokenORM).filter(
        models.PasswordResetTokenORM.user_id == user.id,
        models.PasswordResetTokenORM.used_at.is_(None),
    ).update({"used_at": utc_now_naive()}, synchronize_session=False)

    # Создаём новый.
    token = secrets.token_urlsafe(32)
    expires_at = utc_now_naive() + timedelta(hours=1)

    ip = (
        request.headers.get("x-forwarded-for", "")
        .split(",")[0]
        .strip()
        or (request.client.host if request.client else None)
    )

    db.add(models.PasswordResetTokenORM(
        token=token,
        user_id=user.id,
        created_at=utc_now_naive(),
        expires_at=expires_at,
        requester_ip=(ip[:64] if ip else None),
    ))
    db.commit()

    # Шлём письмо (best-effort).
    from config import settings as _settings
    reset_url = f"{_settings.PUBLIC_URL}/auth/reset-password?token={token}"
    # Отправка в фоне: response не должен зависеть от времени SMTP-round-trip
    # (иначе timing-oracle отличает существующий email от несуществующего).
    background_tasks.add_task(
        send_password_reset_email,
        to_email=user.email,
        reset_url=reset_url,
        user_name=getattr(user, "name", None),
    )

    log.info("password_reset_request: token issued user_id=%s ip=%s", user.id, ip)
    return response_payload


@router.post("/password-reset/confirm")
@limiter.limit(AUTH_LIMIT)
def password_reset_confirm(
    request: Request,
    payload: schemas.PasswordResetConfirm,
    db: Session = Depends(database.get_db),
):
    """PR 26: установить новый пароль по one-time token.

    Защита:
    - Token used_at != NULL → 400 (одноразовый).
    - expires_at < now → 400.
    - Минимальная длина 12 символов.
    - После успеха — отзываем все активные JWT юзера (force re-login).
    """
    token_row = db.query(models.PasswordResetTokenORM).filter(
        models.PasswordResetTokenORM.token == payload.token
    ).first()

    if token_row is None or token_row.used_at is not None:
        raise HTTPException(status_code=400, detail="Ссылка недействительна или уже использована")

    if token_row.expires_at < utc_now_naive():
        raise HTTPException(status_code=400, detail="Ссылка истекла. Запросите новую.")

    if len(payload.new_password) < 12:
        raise HTTPException(status_code=400, detail="Пароль должен быть минимум 12 символов")

    user = db.query(models.User).filter(models.User.id == token_row.user_id).first()
    if user is None or user.is_active != 1:
        raise HTTPException(status_code=400, detail="Аккаунт недоступен")

    user.hashed_password = auth_service.get_password_hash(payload.new_password)
    token_row.used_at = utc_now_naive()
    # API-07: инвалидируем все активные JWT (выпущенные до этого момента).
    user.tokens_valid_after = utc_now_naive()
    db.commit()

    log.info("password_reset_confirm: password changed user_id=%s", user.id)

    return {"message": "Пароль успешно изменён. Войдите с новым паролем."}


# ==================== OAuth ENDPOINTS ====================

def _assert_allowed_redirect(uri: str) -> None:
    """API-08: серверный allowlist redirect_uri (exact-match, anti open-redirect).

    Default-allowlist пуст → любой redirect_uri отклоняется, пока не сконфигурён.
    Exact-match намеренно: prefix/startswith открывали бы open-redirect."""
    from config import settings
    if uri not in settings.OAUTH_ALLOWED_REDIRECT_URIS:
        raise HTTPException(status_code=400, detail="redirect_uri не разрешён")


@router.get("/oauth/providers")
def get_oauth_providers():
    """
    Получить список доступных OAuth провайдеров.
    """
    return oauth_service.get_available_providers()


@router.get("/oauth/{provider}/authorize")
@limiter.limit(AUTH_LIMIT)
def oauth_authorize(request: Request, provider: str, redirect_uri: str):
    """
    Получить URL для авторизации через OAuth провайдера.
    Rate limit: 5 запросов в минуту.
    """
    _assert_allowed_redirect(redirect_uri)

    oauth_provider = oauth_service.get_provider(provider)
    if not oauth_provider:
        raise HTTPException(status_code=400, detail=f"Провайдер {provider} не поддерживается или не настроен")

    state = secrets.token_urlsafe(32)

    # PKCE: генерируем pair и сохраняем verifier рядом со state.
    # На callback verifier придёт обратно через стор и пойдёт в token-exchange.
    code_verifier, code_challenge = oauth_service.generate_pkce_pair()
    oauth_store.set(state, provider, code_verifier=code_verifier)

    auth_url = oauth_provider.get_authorize_url(
        redirect_uri, state, code_challenge=code_challenge
    )
    return {"authorize_url": auth_url, "state": state}


@router.post("/oauth/{provider}/callback")
@limiter.limit(AUTH_LIMIT)
async def oauth_callback(
    request: Request,
    response: Response,
    provider: str,
    code: str,
    state: str,
    redirect_uri: str,
    db: Session = Depends(database.get_db)
):
    """
    Обработать callback от OAuth провайдера и создать/авторизовать пользователя.

    Использует PKCE: code_verifier забирается из стора по state и передаётся
    в exchange — защита от перехвата authorization code.
    """
    _assert_allowed_redirect(redirect_uri)

    state_record = oauth_store.consume(state, provider)
    if state_record is None:
        raise HTTPException(status_code=400, detail="Неверный state параметр")

    oauth_provider = oauth_service.get_provider(provider)
    if not oauth_provider:
        raise HTTPException(status_code=400, detail=f"Провайдер {provider} не поддерживается")

    try:
        token_data = await oauth_service.exchange_code_for_token(
            oauth_provider, code, redirect_uri,
            code_verifier=state_record.code_verifier,
        )
        access_token = token_data.get("access_token")
        
        if not access_token:
            raise HTTPException(status_code=400, detail="Не удалось получить access_token")
        
        raw_user_info = await oauth_service.get_user_info(oauth_provider, access_token)
        user_info = oauth_service.normalize_user_info(provider, raw_user_info)
        
        email = user_info.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="Email не получен от провайдера")
        
        user = db.query(models.User).filter(models.User.email == email).first()
        
        if user:
            if user.oauth_provider != provider:
                user.oauth_provider = provider
                user.oauth_provider_id = user_info.get("provider_id")
            user.last_login = utc_now_naive()
            db.commit()
        else:
            user = models.User(
                email=email,
                name=user_info.get("name"),
                hashed_password=None,
                oauth_provider=provider,
                oauth_provider_id=user_info.get("provider_id"),
                registration_source=provider,
                last_login=utc_now_naive(),
                is_active=1,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            # Idempotent создание дефолтного счёта (фикс дубликата #5).
            existing = db.query(models.Account).filter(
                models.Account.user_id == user.id
            ).first()
            if existing is None:
                default_account = models.Account(
                    user_id=user.id,
                    name="Основной",
                    balance=0,
                    currency="RUB"
                )
                db.add(default_account)
                db.commit()

            log.info("👤 Создан OAuth пользователь: user_id=%s через %s", user.id, provider)

        # S1-06b: OAuth-юзер с включённым TOTP не получает полную сессию до
        # проверки 6-значного кода — иначе 2FA была бы фиктивной защитой
        # (OAuth-юзеры часто без пароля и не могут пройти /auth/login).
        if user.totp_enabled:
            pending_token = auth_service.create_2fa_pending_token(user.id)
            log.info("🔐 OAuth вход требует 2FA: user_id=%s через %s", user.id, provider)
            return {
                "two_factor_required": True,
                "pending_token": pending_token,
            }

        # Создаём пару токенов
        access_token, refresh_token = auth_service.create_token_pair(user.id, user.email)
        auth_service.set_auth_cookies(response, request, access_token, refresh_token)

        log.info("🔐 OAuth вход: user_id=%s через %s", user.id, provider)

        # SEC-08: токены отдаём только в httpOnly cookies; в теле — лишь
        # non-secret user-блок + метаданные сессии.
        return {
            "token_type": "bearer",
            "expires_in": auth_service.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "authenticated": True,
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "oauth_provider": user.oauth_provider,
            }
        }

    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        log.warning(f"⏱️ OAuth timeout for {provider}: {exc}")
        raise HTTPException(status_code=504, detail="OAuth провайдер не ответил вовремя")
    except httpx.HTTPStatusError as exc:
        log.warning(f"❌ OAuth provider HTTP error for {provider}: {exc}")
        raise HTTPException(status_code=502, detail="Ошибка ответа OAuth провайдера")
    except httpx.HTTPError as exc:
        log.warning(f"❌ OAuth transport error for {provider}: {exc}")
        raise HTTPException(status_code=502, detail="Ошибка соединения с OAuth провайдером")
    except Exception as exc:
        log.error(f"❌ OAuth ошибка для {provider}: {exc}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка OAuth авторизации")


@router.post("/oauth/2fa/verify", response_model=schemas.AuthSuccess)
@limiter.limit(AUTH_LIMIT)
def oauth_2fa_verify(
    request: Request,
    response: Response,
    payload: schemas.OAuth2faVerifyRequest,
    db: Session = Depends(database.get_db),
):
    """S1-06b: завершить OAuth-вход для юзера с включённым 2FA.

    Принимает pending-токен (выданный /auth/oauth/{provider}/callback) +
    6-значный TOTP код. При успехе — полная сессия (cookies), как обычный
    OAuth-вход. Rate limit: 5 запросов в минуту (защита от brute-force кода).
    """
    from services.totp_service import verify_code_for_user

    user_id = auth_service.decode_2fa_pending_token(payload.pending_token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Сессия истекла. Войдите заново.")

    user = auth_service.get_user_by_id(db, user_id)
    if user is None or user.is_active != 1:
        raise HTTPException(status_code=401, detail="Сессия истекла. Войдите заново.")

    if not user.totp_enabled or not verify_code_for_user(user, payload.code, db=db):
        raise HTTPException(status_code=401, detail="Неверный код двухфакторной аутентификации")

    # S4-10: персистим totp_last_used_step ДО выдачи токенов (см. login).
    db.commit()

    access_token, refresh_token = auth_service.create_token_pair(user.id, user.email)
    auth_service.set_auth_cookies(response, request, access_token, refresh_token)

    log.info("🔐 OAuth 2FA подтверждён: user_id=%s", user.id)

    return {
        "token_type": "bearer",
        "expires_in": auth_service.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "authenticated": True,
    }
