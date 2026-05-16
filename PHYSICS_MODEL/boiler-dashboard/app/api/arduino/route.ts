import { NextResponse } from 'next/server';

// Connect to the local Python Serial USB proxy
const ESP32_IP = "127.0.0.1:8080";

// We set this to true if the physical Arduino endpoint goes away, to preserve last known state
// rather than crashing out the web app frontend.
let lastKnownState = {
  mw: 0.0,
  Q: 0.0,
  Kv: 0.0,
  T: 0.0,
  P: 1.013,
  pump: 0,
  ip: "0.0.0.0",
  connected: false
};

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const isPredict = searchParams.get('predict') === 'true';
  const isExport = searchParams.get('export') === 'true';

  // Build the proxy endpoint URL
  let endpoint = isExport ? 'export' : (isPredict ? 'predict' : 'data');
  if (isPredict) {
    const minutes = searchParams.get('minutes');
    const targetPressure = searchParams.get('target_pressure');
    const rFouling = searchParams.get('r_fouling');
    const params = new URLSearchParams();
    if (minutes) params.set('minutes', minutes);
    if (targetPressure) params.set('target_pressure', targetPressure);
    if (rFouling) params.set('r_fouling', rFouling);
    const qs = params.toString();
    if (qs) endpoint += `?${qs}`;
  }

  try {
    const res = await fetch(`http://${ESP32_IP}/${endpoint}`, {
      method: "GET",
      // Prediction needs more time than telemetry (physics solver)
      signal: AbortSignal.timeout(isPredict ? 15000 : 5000), 
      cache: 'no-store', 
      headers: {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
      }
    });

    if (res.ok) {
      if (isExport) {
        // Return the binary CSV file
        const blob = await res.blob();
        return new Response(blob, {
          headers: {
            'Content-Type': 'text/csv',
            'Content-Disposition': res.headers.get('Content-Disposition') || 'attachment; filename="session.csv"'
          }
        });
      }

      const data = await res.json();
      
      // If it's a telemetry request (not predict), update lastKnownState
      if (!isPredict) {
        lastKnownState = {
          ...data,
          connected: true
        };
      }
      
      return NextResponse.json({
        ...data,
        connected: true
      });
    } else {
      return NextResponse.json({ ...lastKnownState, connected: false }, { status: 502 });
    }
  } catch (error) {
    console.error("GET /api/arduino error:", error);
    return NextResponse.json({ ...lastKnownState, connected: false }, { status: 504 });
  }
}

export async function POST(req: Request) {
  try {
    const body = await req.json();
    console.log("🚀 [API Route] Forwarding POST body:", JSON.stringify(body));
    
    // Forward the control command to the local Python Proxy
    const res = await fetch(`http://${ESP32_IP}/control`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });

    if (res.ok) {
      const data = await res.json();
      return NextResponse.json(data);
    } else {
      return NextResponse.json({ error: "Failed to send command to proxy" }, { status: 502 });
    }
  } catch (error) {
    console.error("POST /api/arduino error:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
