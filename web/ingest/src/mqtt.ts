import mqtt, { type MqttClient } from 'mqtt';

// Wildcard `+` for devEui always applies - one node's uplinks look identical
// to another's on the wire, so there is no reason to enumerate devices here.
// The application ID segment is only pinned down when CHIRPSTACK_APPLICATION_ID
// is set, so a shared local broker with several test applications on it
// doesn't cross-contaminate this bridge's inserts.
function uplinkTopic(): string {
  const appId = process.env.CHIRPSTACK_APPLICATION_ID;
  return appId ? `application/${appId}/device/+/event/up` : 'application/+/device/+/event/up';
}

export function connectMqtt(onUplink: (payload: unknown) => Promise<void>): MqttClient {
  const url = process.env.MQTT_URL!;
  const topic = uplinkTopic();
  const client = mqtt.connect(url);

  client.on('connect', () => {
    console.log(`Connected to MQTT broker at ${url}`);
    client.subscribe(topic, (err, granted) => {
      if (err) {
        console.error(`Failed to subscribe to ${topic}:`, err);
        process.exit(1);
      }
      console.log(`Subscribed to ${topic}, granted:`, JSON.stringify(granted));
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
    onUplink(payload).catch((err) => {
      console.error(`Failed to process uplink from ${topic}:`, err);
    });
  });

  client.on('error', (err) => console.error('MQTT client error:', err));
  client.on('close', () => console.warn('MQTT connection closed'));
  client.on('reconnect', () => console.warn('MQTT reconnecting...'));
  client.on('offline', () => console.warn('MQTT client offline'));

  return client;
}
