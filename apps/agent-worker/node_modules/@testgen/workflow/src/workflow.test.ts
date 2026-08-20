import { describe, expect, it } from 'vitest';
import { assertTransition } from './index.js';

describe('workflow state machine', () => {
  it('allows queueing a created run', () => expect(() => assertTransition('CREATED', 'QUEUED')).not.toThrow());
  it('rejects terminal state mutation', () => expect(() => assertTransition('SUCCEEDED', 'RUNNING')).toThrow());
});
