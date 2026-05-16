export function ToggleSwitch({ active, onToggle }: { active: boolean; onToggle: () => void }) {
  return (
    <button
      className={`toggle-switch ${active ? 'active' : ''}`}
      onClick={onToggle}
      style={{ position: 'relative', display: 'flex', alignItems: 'center' }}
    />
  );
}
