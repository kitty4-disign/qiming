import assert from "node:assert/strict";
import test from "node:test";

import { UnifiedWSClient } from "../lib/unified-ws";


class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  static instances: FakeWebSocket[] = [];

  readyState = FakeWebSocket.CONNECTING;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: ((error: unknown) => void) | null = null;

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(payload: string): void {
    this.sent.push(payload);
  }

  close(): void {
    this.readyState = FakeWebSocket.CLOSED;
  }

  open(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }
}


test("messages wait for a slow WebSocket handshake", () => {
  FakeWebSocket.instances = [];
  Object.assign(globalThis, { WebSocket: FakeWebSocket });
  const client = new UnifiedWSClient(() => undefined);

  client.connect();
  client.send({ type: "start_turn", content: "hello" });

  const socket = FakeWebSocket.instances[0];
  assert.equal(socket.sent.length, 0);

  socket.open();
  assert.deepEqual(socket.sent.map((payload) => JSON.parse(payload)), [
    { type: "start_turn", content: "hello" },
  ]);
  client.disconnect();
});


test("disconnect drops messages that were never sent", () => {
  FakeWebSocket.instances = [];
  Object.assign(globalThis, { WebSocket: FakeWebSocket });
  const client = new UnifiedWSClient(() => undefined);

  client.connect();
  client.send({ type: "start_turn", content: "stale" });
  client.disconnect();
  client.connect();
  const socket = FakeWebSocket.instances[1];
  socket.open();

  assert.equal(socket.sent.length, 0);
  client.disconnect();
});


test("education context is serialized outside capability config", () => {
  FakeWebSocket.instances = [];
  Object.assign(globalThis, { WebSocket: FakeWebSocket });
  const client = new UnifiedWSClient(() => undefined);
  client.connect();
  const socket = FakeWebSocket.instances[0];
  socket.open();

  client.send({
    type: "start_turn",
    content: "start lesson",
    config: {
      course_id: "image-recognition",
      mastery_path_id: "edu_k12_ai_primary_upper_image_recognition",
    },
    education_context: {
      stage: "primary_upper",
      grade: 5,
      knowledge_point_id: "path_m0_kp0",
    },
  });

  const payload = JSON.parse(socket.sent[0]);
  assert.equal(payload.config.stage, undefined);
  assert.deepEqual(payload.education_context, {
    stage: "primary_upper",
    grade: 5,
    knowledge_point_id: "path_m0_kp0",
  });
  client.disconnect();
});
