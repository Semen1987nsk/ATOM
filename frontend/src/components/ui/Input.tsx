import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";
import { clsx } from "clsx";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
  leftIcon?: ReactNode;
  rightAddon?: ReactNode;
  fullWidth?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, leftIcon, rightAddon, fullWidth = true, className, id, ...rest },
  ref,
) {
  const inputId = id ?? rest.name;
  return (
    <div className={clsx("flex flex-col gap-1.5", fullWidth && "w-full")}>
      {label && (
        <label
          htmlFor={inputId}
          className="text-[13px] font-medium text-[var(--text-secondary)]"
        >
          {label}
        </label>
      )}
      <div className="relative flex items-center">
        {leftIcon && (
          <div className="absolute left-3 flex items-center pointer-events-none text-[var(--text-tertiary)]">
            {leftIcon}
          </div>
        )}
        <input
          ref={ref}
          id={inputId}
          className={clsx(
            "input-cyber",
            leftIcon && "pl-10",
            rightAddon && "pr-10",
            error && "border-[var(--danger)] focus:border-[var(--danger)]",
            className,
          )}
          aria-invalid={!!error}
          aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined}
          {...rest}
        />
        {rightAddon && (
          <div className="absolute right-3 flex items-center text-[var(--text-tertiary)]">
            {rightAddon}
          </div>
        )}
      </div>
      {error ? (
        <p id={`${inputId}-error`} className="text-[12px] text-[var(--danger)]">
          {error}
        </p>
      ) : hint ? (
        <p id={`${inputId}-hint`} className="text-[12px] text-[var(--text-tertiary)]">
          {hint}
        </p>
      ) : null}
    </div>
  );
});
