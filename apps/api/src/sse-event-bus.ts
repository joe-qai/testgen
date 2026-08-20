import { EventEmitter } from 'node:events';
import type { WorkflowEventRecord } from '@testgen/workflow';

export type SseChunk = string;

export class SseEventBus {
  private readonly emitter = new EventEmitter();

  subscribe(runId: string, onChunk: (chunk: SseChunk) => void): () => void {
    const listener = (chunk: SseChunk) => onChunk(chunk);
    this.emitter.on(runId, listener);
    return () => { this.emitter.off(runId, listener); };
  }

  publish(runId: string, event: WorkflowEventRecord): void {
    const chunk = `id: ${event.sequence}\nevent: ${event.eventType}\ndata: ${JSON.stringify(event)}\n\n`;
    this.emitter.emit(runId, chunk);
  }

  subscriberCount(runId: string): number {
    return this.emitter.listenerCount(runId);
  }
}