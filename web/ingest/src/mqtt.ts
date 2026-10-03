import mqtt, { type IPublishPacket, type MqttClient } from 'mqtt';
import { ACK_RETRY, withRetry } from './retry.js';

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

  // The uplink is handled here, in handleMessage, rather than in a 'message'
  // listener, and that placement is the whole point.
  //
  // mqtt.js sends the QoS 1 PUBACK when this callback fires (see
  // lib/handlers/publish.js) - so acking late, after the row is in Supabase,
  // costs nothing but moving the work here. Handling it in a 'message'
  // listener acked the frame the instant it arrived, before the write was
  // even attempted, which made the persistent session decorative: a frame
  // that arrived during a Supabase outage was acked, dropped from the
  // broker's store, and then lost when the write failed. The broker thought
  // it had been delivered because, as far as MQTT was concerned, it had.
  //
  // Not calling back is a deliberate state, not an oversight. While a write
  // is still being retried the frame stays unacked and stays in the broker's
  // store; if this process dies it is redelivered on reconnect. That also
  // throttles us for free - mosquitto stops sending once its in-flight window
  // (max_inflight_messages, 20 by default) is full - so a long outage backs up
  // in the broker, which has persistence on and survives a restart, rather
  // than in this process's heap.
  //
  // The hazard that creates is a message that can never succeed holding the
  // window shut against every real alert behind it. ACK_RETRY's isPermanent
  // closes that: a frame rejected for what it contains is acked and dropped
  // loudly, and only infrastructure failures are waited on.
  //
  // Note that 'message' is emitted before this runs, so the work must be in
  // one place or the other. Doing it in both would write every uplink twice.
  client.handleMessage = (packet: IPublishPacket, callback: (err?: Error) => void) => {
    const topic = packet.topic;
    const raw = packet.payload;
    console.log(`Received message on ${topic} (${raw.length} bytes)`);

    let payload: unknown;
    try {
      payload = JSON.parse(raw.toString());
    } catch (err) {
      // Unparseable now is unparseable on every redelivery. Ack it, or it
      // sits at the head of the in-flight window forever and nothing behind
      // it is ever delivered.
      console.error(`Ignoring non-JSON message on ${topic}:`, err);
      callback();
      return;
    }

    withRetry(`uplink from ${topic}`, () => onUplink(payload), ACK_RETRY).then(
      () => callback(),
      (err) => {
        // ACK_RETRY never gives up on a transient failure, so reaching here
        // means isPermanent said the frame itself is the problem. It has
        // already been logged; ack it so the queue moves.
        console.error(`Dropping unwritable uplink from ${topic}:`, err);
        callback();
      },
    );
  };

  client.on('error', (err) => console.error('MQTT client error:', err));
  client.on('close', () => console.warn('MQTT connection closed'));
  client.on('reconnect', () => console.warn('MQTT reconnecting...'));
  client.on('offline', () => console.warn('MQTT client offline'));

  return client;
}
