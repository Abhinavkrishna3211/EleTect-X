import 'dotenv/config';
import { connectMqtt } from './mqtt.js';
import { handleUplink } from './uplink.js';

const REQUIRED_ENV = ['SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'MQTT_URL'] as const;

for (const key of REQUIRED_ENV) {
  if (!process.env[key]) {
    console.error(`Missing required env var ${key}. Copy .env.example to .env and fill it in.`);
    process.exit(1);
  }
}

connectMqtt(handleUplink);
