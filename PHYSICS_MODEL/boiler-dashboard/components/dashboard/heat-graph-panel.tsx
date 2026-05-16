import { useMemo } from "react";
import { HeatGraph3D } from "./heat-graph-3d";

interface LiveData {
  mw: number;
  Q: number;
  Kv?: number;
  T: number;
  P: number;
  pump: number;
  connected: boolean;
  [key: string]: any;
}

export function HeatGraphPanel({ liveData }: { liveData: LiveData }) {
  const GRID = 32;

  // Thermal Map generation synced to live Temperature (T) and Heater (Q)
  const temperatureData = useMemo(() => {
    const data: number[][] = [];
    const baseT = liveData.T || 25;
    const heaterInfluence = liveData.Q / 50; 
    
    for (let y = 0; y < GRID; y++) {
      const row: number[] = [];
      for (let x = 0; x < GRID; x++) {
        const nx = x / GRID, ny = y / GRID;
        const core = (heaterInfluence + 40) * Math.exp(-((nx - 0.45) ** 2 + (ny - 0.6) ** 2) / 0.04);
        const steam = (baseT * 0.4) * Math.exp(-((nx - 0.5) ** 2 + (ny - 0.2) ** 2) / 0.05);
        const water = (baseT * 0.2) * Math.exp(-((nx - 0.3) ** 2 + (ny - 0.4) ** 2) / 0.06);
        const inlet = -15 * Math.exp(-((nx - 0.15) ** 2 + (ny - 0.8) ** 2) / 0.03);
        const temp = (baseT * 0.6) + core + steam + water + inlet + (Math.random() * 2 - 1);
        row.push(Math.max(20, Math.min(450, temp)));
      }
      data.push(row);
    }
    return data;
  }, [liveData.T, liveData.Q]);

  // Pressure Threshold Mesh synced to absolute Pressure (P)
  const pressureData = useMemo(() => {
    const data: number[][] = [];
    const pGauge = Math.max(0, liveData.P - 1.013);
    const pScale = pGauge * 3; // exaggerate for visual effect

    for (let y = 0; y < GRID; y++) {
      const row: number[] = [];
      for (let x = 0; x < GRID; x++) {
        const nx = x / GRID, ny = y / GRID;
        const drumTop = (pScale * 0.8 + 0.2) * Math.exp(-((nx - 0.5) ** 2 + (ny - 0.2) ** 2) / 0.08);
        const steamZone = (pScale * 0.4 + 0.1) * Math.exp(-((nx - 0.4) ** 2 + (ny - 0.15) ** 2) / 0.05);
        const valveDrop = -((liveData.Kv ?? 0) * 0.4) * Math.exp(-((nx - 0.75) ** 2 + (ny - 0.2) ** 2) / 0.02);
        const baseP = (pScale * 0.2) + drumTop + steamZone + valveDrop + (Math.random() * 0.01 - 0.005);
        row.push(Math.max(0.01, Math.min(5.0, baseP)));
      }
      data.push(row);
    }
    return data;
  }, [liveData.P, liveData.Kv]);

  // Fluid Dynamics synced to Flow Rate (mw) and Pump status
  const waterLevelData = useMemo(() => {
    const data: number[][] = [];
    const flow = liveData.mw || 0;
    const pumpActive = liveData.pump === 1;

    for (let y = 0; y < GRID; y++) {
      const row: number[] = [];
      for (let x = 0; x < GRID; x++) {
        const nx = x / GRID, ny = y / GRID;
        const baseLevel = 30 + flow * 2;
        const drumCenter = 30 * Math.exp(-((nx - 0.5) ** 2 + (ny - 0.5) ** 2) / 0.15);
        const slosh = (pumpActive ? 18 : 6) * Math.sin(nx * 10 + ny * 8) * Math.cos(ny * 4) * Math.exp(-((nx - 0.5) ** 2 + (ny - 0.5) ** 2) / 0.5);
        const feedInlet = (flow * 4) * Math.exp(-((nx - 0.1) ** 2 + (ny - 0.8) ** 2) / 0.03);
        const level = baseLevel + drumCenter + slosh + feedInlet + (Math.random() * 1.5 - 0.75);
        row.push(Math.max(5, Math.min(100, level)));
      }
      data.push(row);
    }
    return data;
  }, [liveData.mw, liveData.pump]);

  // Yield Topology synced to Heater (Q) and Efficiency trends
  const efficiencyData = useMemo(() => {
    const data: number[][] = [];
    const heaterVal = liveData.Q / 1000; // kW
    
    for (let y = 0; y < GRID; y++) {
      const row: number[] = [];
      for (let x = 0; x < GRID; x++) {
        const nx = x / GRID, ny = y / GRID;
        const optimal = (heaterVal * 15 + 5) * Math.exp(-((nx - 0.4) ** 2 + (ny - 0.4) ** 2) / 0.1);
        const combustion = (heaterVal * 10 + 6) * Math.exp(-((nx - 0.6) ** 2 + (ny - 0.5) ** 2) / 0.07);
        const heatLoss = -12 * (Math.pow(nx - 0.5, 2) + Math.pow(ny - 0.8, 2));
        const boundaryLoss = -6 * (Math.pow(nx, 2) + Math.pow(ny, 2));
        const eff = 75 + optimal + combustion + heatLoss + boundaryLoss + (Math.random() * 1.0 - 0.5);
        row.push(Math.max(50, Math.min(99, eff)));
      }
      data.push(row);
    }
    return data;
  }, [liveData.Q]);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '24px' }}>
      <div className="animate-fade-up delay-4">
        <HeatGraph3D
          title="Thermal Map Surface"
          subtitle="Boiler vessel 32-point continuous heat scan calculation"
          unit="°C"
          glowColor="rgba(255,50,0)"
          accentGradient="linear-gradient(90deg, transparent, rgba(255,50,0,0.6), rgba(200,0,0,0.4), transparent)"
          data={temperatureData}
        />
      </div>
      <div className="animate-fade-up delay-5">
        <HeatGraph3D
          title="Pressure Threshold Mesh"
          subtitle="Steam drum differential gradient representation"
          unit="MPa"
          glowColor="rgba(0,180,255)"
          accentGradient="linear-gradient(90deg, transparent, rgba(0,180,255,0.6), rgba(0,100,200,0.4), transparent)"
          data={pressureData}
        />
      </div>
      <div className="animate-fade-up delay-6">
        <HeatGraph3D
          title="Dynamic Fluid Dynamics"
          subtitle="Active volumetric capacity wave modeling"
          unit="%"
          glowColor="rgba(150,100,250)"
          accentGradient="linear-gradient(90deg, transparent, rgba(150,100,250,0.6), rgba(100,50,200,0.4), transparent)"
          data={waterLevelData}
        />
      </div>
      <div className="animate-fade-up delay-7">
        <HeatGraph3D
          title="Yield Topology"
          subtitle="Analytical energy retention contour mapping"
          unit="%"
          glowColor="rgba(100,250,50)"
          accentGradient="linear-gradient(90deg, transparent, rgba(100,250,50,0.6), rgba(0,150,50,0.4), transparent)"
          data={efficiencyData}
        />
      </div>
    </div>
  );
}
