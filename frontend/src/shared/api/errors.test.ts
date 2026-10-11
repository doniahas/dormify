import { describe, expect, it } from 'vitest';
import MockAdapter from 'axios-mock-adapter';
import { api, ApiError, getErrorMessage, throwApiError } from './client';
import { errorCode, errorStatus, isApiError, normalizeApiError } from './errors';

const mock = new MockAdapter(api, { onNoMatch: 'throwException' });

async function failing(status: number, body: unknown): Promise<unknown> {
  mock.reset();
  mock.onGet('/api/probe/').reply(status, body);
  try {
    await api.get('/api/probe/');
  } catch (err) {
    return err;
  }
  throw new Error('request unexpectedly succeeded');
}

describe('normalizeApiError', () => {
  it('reads a hand-written {error} body with the same message the client flattens', async () => {
    const err = await failing(403, { error: 'אין הרשאה לאזור זה' });
    const normalized = normalizeApiError(err);
    // The client prefixes a bare {error} body with its key; the normalizer
    // keeps that text as `message` and exposes the bare sentence separately.
    expect(normalized).toMatchObject({ kind: 'http', status: 403, message: 'error: אין הרשאה לאזור זה', serverMessage: 'אין הרשאה לאזור זה', code: null });
    expect(normalized.message).toBe(getErrorMessage(err));
    expect(normalized.fieldErrors).toBeNull();
  });

  it('exposes the English twin, the error code and the conflicting status', async () => {
    const err = await failing(409, {
      success: false,
      error: 'כבר רץ שיבוץ עבור אזור זה',
      error_code: 'ALLOCATION_ALREADY_RUNNING',
      region: 'north',
      run_id: 41,
    });
    expect(normalizeApiError(err)).toMatchObject({
      status: 409, code: 'ALLOCATION_ALREADY_RUNNING', messageEn: null, conflictStatus: null,
    });

    const stopped = await failing(409, { error: 'ניתן לעצור רק קובץ שנמצא כרגע בעיבוד', errorEn: 'Only a batch currently processing can be stopped', status: 'pending' });
    expect(normalizeApiError(stopped)).toMatchObject({
      messageEn: 'Only a batch currently processing can be stopped', conflictStatus: 'pending',
    });
  });

  it('recognizes DRF field-keyed validation dicts and structured rule violations', async () => {
    const fields = await failing(400, { housing_type: ['יש לבחור סוג דיור לפני שניתן לבצע שיבוץ.'] });
    expect(normalizeApiError(fields).fieldErrors).toEqual({ housing_type: ['יש לבחור סוג דיור לפני שניתן לבצע שיבוץ.'] });
    expect(normalizeApiError(fields).structured).toBeNull();

    const rule = await failing(400, { field: 'capacity', code: 'CAPACITY_BELOW_OCCUPANCY', message: 'x' });
    const normalized = normalizeApiError(rule);
    expect(normalized.structured).toEqual({ field: 'capacity', code: 'CAPACITY_BELOW_OCCUPANCY', message: 'x' });
    expect(normalized.code).toBe('CAPACITY_BELOW_OCCUPANCY');
    expect(normalized.fieldErrors).toBeNull();
  });

  it('keeps the status and field errors of an ApiError thrown by the client', async () => {
    const raw = await failing(400, { student_id: ['already exists'] });
    let thrown: unknown;
    try {
      throwApiError(raw, 'Failed');
    } catch (err) {
      thrown = err;
    }
    expect(isApiError(thrown)).toBe(true);
    expect(thrown).toBeInstanceOf(ApiError);
    expect(normalizeApiError(thrown)).toMatchObject({
      kind: 'http', status: 400, message: 'student_id: already exists', serverMessage: null, fieldErrors: { student_id: ['already exists'] },
    });
  });

  it('classifies transport failures, cancellations, strings and wrapped errors', async () => {
    mock.reset();
    mock.onGet('/api/probe/').networkError();
    let network: unknown;
    try {
      await api.get('/api/probe/');
    } catch (err) {
      network = err;
    }
    expect(normalizeApiError(network)).toMatchObject({ kind: 'network', status: null });
    expect(normalizeApiError(network).message).toBe(getErrorMessage(network));

    expect(normalizeApiError({ code: 'ERR_CANCELED', message: 'canceled' })).toMatchObject({ kind: 'cancelled', status: null });
    expect(normalizeApiError('plain text')).toMatchObject({ kind: 'unknown', message: 'plain text' });
    expect(normalizeApiError(new Error('Failed to load'))).toMatchObject({ kind: 'unknown', message: 'Failed to load', status: null });
    expect(normalizeApiError(undefined, 'Fallback').message).toContain('Fallback');
  });

  it('offers status and code shortcuts', async () => {
    const err = await failing(404, { error: 'הרצה לא נמצאה' });
    expect(errorStatus(err)).toBe(404);
    expect(errorCode(err)).toBeNull();
    expect(errorStatus(new Error('x'))).toBeNull();
  });
});
