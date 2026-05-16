import { Activity, Droplets, Thermometer, Gauge } from "lucide-react";

export const STAT_CARDS = [
  {
    id: 'pressure',
    label: 'Pressure',
    value: '1.24',
    unit: 'MPa',
    trend: +2,
    bar: 75,
    sub: 'Range 1.20 – 1.30 MPa',
    icon: Gauge,
    accent: '#0071e3',
    accentAlpha: 'rgba(0,113,227,0.10)',
    description: 'Drum pressure within safe operating band',
  },
  {
    id: 'temperature',
    label: 'Temperature',
    value: '350',
    unit: '°C',
    trend: -5,
    bar: 85,
    sub: 'Expected 340 °C average',
    icon: Thermometer,
    accent: '#ff9f0a',
    accentAlpha: 'rgba(255,159,10,0.10)',
    description: 'Slightly above baseline — monitor trend',
  },
  {
    id: 'water',
    label: 'Water Level',
    value: '65.2',
    unit: '%',
    trend: +1,
    bar: 65,
    sub: 'Nominal 55 – 75 %',
    icon: Droplets,
    accent: '#5e5ce6',
    accentAlpha: 'rgba(94,92,230,0.10)',
    description: 'Level stable within nominal range',
  },
  {
    id: 'efficiency',
    label: 'Efficiency',
    value: '94.8',
    unit: '%',
    trend: +3,
    bar: 95,
    sub: 'Target ≥ 90 %',
    icon: Activity,
    accent: '#30d158',
    accentAlpha: 'rgba(48,209,88,0.10)',
    description: 'Exceeding efficiency target by 4.8 pp',
  },
] as const;

export const STATUS_ROWS = [
  { label: 'Drum Pressure', value: 'Normal',  color: '#1a8f3c', type: 'green' },
  { label: 'Water Level',   value: 'Normal',  color: '#1a8f3c', type: 'green' },
  { label: 'Combustion',    value: 'Active',  color: '#0071e3', type: 'blue'  },
  { label: 'Safety Valve',  value: 'Sealed',  color: '#1a8f3c', type: 'green' },
  { label: 'Feed Pump',     value: 'Running', color: '#0071e3', type: 'blue'  },
] as const;

export const TELEMETRY = [
  { time: '10:50 AM', date: 'Apr 10, 2026', p: '1.24', l: '65.2', t: '350', status: 'Optimal' },
  { time: '10:45 AM', date: 'Apr 10, 2026', p: '1.22', l: '64.8', t: '348', status: 'Optimal' },
  { time: '10:40 AM', date: 'Apr 10, 2026', p: '1.35', l: '60.1', t: '365', status: 'Warning' },
  { time: '10:35 AM', date: 'Apr 10, 2026', p: '1.20', l: '63.5', t: '349', status: 'Optimal' },
] as const;

export const ANALYTICS_DATA = [
  { time: '10:00 AM', pressure: 1.20, temperature: 340, waterLevel: 60, vP: 50, vT: 60, vW: 50 },
  { time: '10:05 AM', pressure: 1.22, temperature: 342, waterLevel: 62, vP: 40, vT: 55, vW: 60 },
  { time: '10:10 AM', pressure: 1.25, temperature: 345, waterLevel: 65, vP: 30, vT: 40, vW: 75 },
  { time: '10:15 AM', pressure: 1.23, temperature: 343, waterLevel: 64, vP: 20, vT: 45, vW: 80 },
  { time: '10:20 AM', pressure: 1.21, temperature: 341, waterLevel: 63, vP: 30, vT: 55, vW: 70 },
  { time: '10:25 AM', pressure: 1.24, temperature: 346, waterLevel: 61, vP: 50, vT: 65, vW: 50 },
  { time: '10:30 AM', pressure: 1.28, temperature: 352, waterLevel: 58, vP: 70, vT: 60, vW: 30 },
  { time: '10:35 AM', pressure: 1.20, temperature: 349, waterLevel: 63, vP: 80, vT: 50, vW: 20 },
  { time: '10:40 AM', pressure: 1.35, temperature: 365, waterLevel: 60, vP: 70, vT: 55, vW: 40 },
  { time: '10:45 AM', pressure: 1.22, temperature: 348, waterLevel: 64, vP: 50, vT: 45, vW: 60 },
  { time: '10:50 AM', pressure: 1.24, temperature: 350, waterLevel: 65, vP: 40, vT: 50, vW: 70 },
];
