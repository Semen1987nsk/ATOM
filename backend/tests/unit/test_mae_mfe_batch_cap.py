from routers import trades as trades_router


def test_batch_cap_constant_exists_and_reasonable():
    assert hasattr(trades_router, "MAE_MFE_BATCH_CAP")
    assert 50 <= trades_router.MAE_MFE_BATCH_CAP <= 500
