import mqtt, { type MqttClient } from 'mqtt';
import { withRetry } from './retry.js';

// Wildcard `+` for devEui always applies - one node's uplinks look identical
// to another's on the wire, so there is no reason to enumerate devices here.
// The application ID segment is only pinned down when CHIRPSTACK_APPLICATION_ID
// is set, so a shared local broker with several test applications on it
// doesn't cross-contaminate this bridge's inserts. It takes a comma-separated
// list, so one bridge can serve the field application and a bench one.
export function uplinkTopics(appIds = process.env.CHIRPSTACK_APPLICATION_ID): string[] {
  const ids = (appIds ?? '').split(',').map((s) => s.trim()).filter(Boolean);
  return ids.length
    ? ids.map((id) => `application/${id}/device/+/event/up`)
    : ['application/+/device/+/event/up'];
}

export function connectMqtt(onUplink: (payload: unknown) => Promise<void>): MqttClient {
  const url = process.env.MQTT_URL!;
  const topics = uplinkTopics();
  // A persistent session (fixed client id, clean: false) at QoS 1 makes the
  // broker hold uplinks while the bridge is restarting or down, and hand them
  // over on reconnect. It only works if ChirpStack also publishes at QoS 1
  // ([integration.mqtt] qos=1) - a QoS 0 message is never queued.
  const client = mqtt.connect(url, {
    clientId: process.env.MQTT_CLIENT_ID || 'eletect-ingest',
    clean: false,
  });

  client.on('connect', () => {
    console.log(`Connected to MQTT broker at ${url}`);
    client.subscribe(topics, { qos: 1 }, (err, granted) => {
      if (err) {
        console.error(`Failed to subscribe to ${topics.join(', ')}:`, err);
        process.exit(1);
      }
      console.log(`Subscribed to ${topics.join(', ')}, granted:`, JSON.stringify(granted));
    });
  });

  client.on('message', (topic, raw) => {
    console.log(`Received message on ${topic} (${raw.length} bytes)`);
    let payload: unknown;
    try {
      payload = JSON.parse(raw.toString());
    } catch (err) {
      console.error(`Ignoring non-JSON message on ${topic}:`, err);
      return;
    }
    withRetry(`uplink from ${topic}`, () => onUplink(payload)).catch(() => {
      // withRetry already logged the final error; nothing left to do.
    });
  });

  client.on('error', (err) => console.error('MQTT client error:', err));
  client.on('close', () => console.warn('MQTT connection closed'));
  client.on('reconnect', () => console.warn('MQTT reconnecting...'));
  client.on('offline', () => console.warn('MQTT client offline'));

  return client;
}
