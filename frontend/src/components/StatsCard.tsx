interface StatsCardProps {
  label: string;
  value: string | number;
  sub?: string;
  accent?: 'green' | 'red' | 'blue' | 'default';
}

export default function StatsCard({ label, value, sub, accent = 'default' }: StatsCardProps) {
  return (
    <div className={`stats-card stats-card--${accent}`}>
      <p className="stats-label">{label}</p>
      <p className="stats-value">{value}</p>
      {sub && <p className="stats-sub">{sub}</p>}
    </div>
  );
}
