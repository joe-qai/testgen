import { describe, expect, it } from 'vitest';
import { SseEventBus } from './sse-event-bus.js';
import type { WorkflowEventRecord } from '@testgen/workflow';

function makeEvent(sequence: number, eventType = 'RUN_STARTED' as const): WorkflowEventRecord {
  return { id: `e-${sequence}`, runId: 'run-1', sequence, eventType, nodeName: null, payload: {}, createdAt: new Date().toISOString() };
}

describe('sse event bus', () => {
  it('delivers published events to subscribers of that run', () => {
    const bus = new SseEventBus();
    const received: string[] = [];
    const unsubscribe = bus.subscribe('run-1', (chunk) => received.push(chunk));
    bus.publish('run-1', makeEvent(0));
    expect(received).toHaveLength(1);
    expect(received[0]).toContain('id: 0');
    expect(received[0]).toContain('event: RUN_STARTED');
    unsubscribe();
    bus.publish('run-1', makeEvent(1));
    expect(received).toHaveLength(1);
  });

  it('only delivers to subscribers of the matching run', () => {
    const bus = new SseEventBus();
    const run1: string[] = [];
    const run2: string[] = [];
    bus.subscribe('run-1', (chunk) => run1.push(chunk));
    bus.subscribe('run-2', (chunk) => run2.push(chunk));
    bus.publish('run-1', makeEvent(0));
    expect(run1).toHaveLength(1);
    expect(run2).toHaveLength(0);
  });

  it('cleans up subscriber on disconnect', () => {
    const bus = new SseEventBus();
    const unsubscribe = bus.subscribe('run-1', () => {});
    expect(bus.subscriberCount('run-1')).toBe(1);
    unsubscribe();
    expect(bus.subscriberCount('run-1')).toBe(0);
  });
});