/**
 * トグルUI（DESIGN.md 第8.3章）。
 *
 * ToggleGroup は「選択肢の配列から1つ選ぶ」汎用トグル。
 * エンジン/API のトグルは ENABLE_ENGINE_TOGGLE=false のとき非表示にし、
 * 既定値を固定表示する（値の強制はサーバー側でも行う）。
 */

export interface ToggleOption<T extends string> {
  value: T;
  label: string;
}

interface ToggleGroupProps<T extends string> {
  label: string;
  options: ToggleOption<T>[];
  value: T;
  onChange: (value: T) => void;
  disabled?: boolean;
}

export function ToggleGroup<T extends string>({
  label,
  options,
  value,
  onChange,
  disabled = false,
}: ToggleGroupProps<T>) {
  return (
    <div className="toggle-group">
      <span className="toggle-label">{label}</span>
      <div className="toggle-buttons">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            className={option.value === value ? 'toggle on' : 'toggle'}
            onClick={() => onChange(option.value)}
            disabled={disabled}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/** トグル非表示時（本番固定時）に、固定されている値を見せるための表示。 */
export function FixedValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="toggle-group">
      <span className="toggle-label">{label}</span>
      <span className="fixed-value">{value}（固定）</span>
    </div>
  );
}
