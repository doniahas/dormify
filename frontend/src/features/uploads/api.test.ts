import { afterEach, describe, expect, it } from 'vitest';
import MockAdapter from 'axios-mock-adapter';
import { api } from '../../shared/api/client';
import { uploadAPI } from './api';

const mock = new MockAdapter(api, { onNoMatch: 'throwException' });
afterEach(() => mock.reset());

describe('import batch handshake', () => {
  it('creates the batch first and reads its status by id', async () => {
    mock.onPost('/api/upload/batches/init/').reply(201, { batch_id: 7, status: 'pending' });
    mock.onGet('/api/upload/batches/7/status/').reply(200, {
      id: 7, kind: 'main', status: 'processing', total_rows: 120, processed_rows: 30,
    });

    await expect(uploadAPI.initBatch('main')).resolves.toEqual({ batch_id: 7, status: 'pending' });
    expect(JSON.parse(mock.history.post[0].data)).toEqual({ kind: 'main' });

    await expect(uploadAPI.getBatchStatus(7)).resolves.toMatchObject({ id: 7, status: 'processing', processed_rows: 30 });
  });

  it('sends the workbook as multipart form data tied to the batch', async () => {
    mock.onPost('/api/upload/excel/').reply(200, { success: true, status: 'processing' });
    mock.onPost('/api/upload/additions-excel/').reply(200, { success: true, status: 'processing' });
    const file = new File(['PK'], 'students.xlsx');

    await expect(uploadAPI.uploadExcel(file, 7)).resolves.toEqual({ success: true, status: 'processing' });
    await uploadAPI.uploadAdditionsExcel(file, 8);

    for (const [index, batchId] of [['0', '7'], ['1', '8']] as const) {
      const request = mock.history.post[Number(index)];
      expect(request.headers?.['Content-Type']).toBe('multipart/form-data');
      const form = request.data as FormData;
      expect(form.get('file')).toBe(file);
      expect(form.get('batch_id')).toBe(batchId);
    }
  });

  it('posts stop, stop-and-delete and delete to their distinct endpoints', async () => {
    mock.onPost('/api/upload/batches/7/stop/').reply(200, { status: 'cancellation_requested' });
    mock.onPost('/api/upload/batches/7/stop-and-delete/').reply(200, { status: 'stop_and_delete_requested' });
    mock.onPost('/api/upload/batches/7/delete/').reply(200, { status: 'deleted' });

    await expect(uploadAPI.stopBatch(7)).resolves.toEqual({ status: 'cancellation_requested' });
    await expect(uploadAPI.stopAndDeleteBatch(7)).resolves.toEqual({ status: 'stop_and_delete_requested' });
    await expect(uploadAPI.deleteBatch(7)).resolves.toEqual({ status: 'deleted' });
    expect(mock.history.post.map(({ url }) => url)).toEqual([
      '/api/upload/batches/7/stop/',
      '/api/upload/batches/7/stop-and-delete/',
      '/api/upload/batches/7/delete/',
    ]);
  });

  it('rejects with the backend explanation, which may be bilingual', async () => {
    mock.onPost('/api/upload/batches/init/').reply(409, { error: 'יש העלאה פעילה', errorEn: 'An upload is already running' });
    await expect(uploadAPI.initBatch('additions')).rejects.toThrow(
      'error: יש העלאה פעילה; errorEn: An upload is already running'
    );

    mock.onGet('/api/upload/batches/9/status/').reply(404, { detail: 'Not found.' });
    await expect(uploadAPI.getBatchStatus(9)).rejects.toThrow('Not found.');
  });
});

describe('batch action contract', () => {
  it('returns the updated batch record for stop, stop-and-delete and delete', async () => {
    const batch = {
      id: 7, uploaded_by: 1, uploaded_by_name: 'Admin', kind: 'main', filename: 'r.xlsx', total_students: 1,
      status: 'stopped', status_display: 'נעצר', error_message: '', created_at: '2026-10-08T08:00:00Z',
      started_at: null, finished_at: '2026-10-08T08:01:00Z', total_rows: 1, processed_rows: 1,
      result: { deletion: { requested: true, deleted_count: 1, protected_count: 0, protected_students: [], performed_at: '2026-10-08T08:01:00Z' } },
      region_breakdown: [{ region_id: 'north', region_name: 'North', count: 1, status: 'pending' }],
    };
    mock.onPost('/api/upload/batches/7/stop-and-delete/').reply(200, batch);
    mock.onPost('/api/upload/batches/7/delete/').reply(409, {
      error: 'ניתן למחוק סטודנטים רק לאחר שההעלאה הסתיימה או נעצרה',
      errorEn: 'Students can only be deleted once the upload has finished or stopped',
      status: 'cancellation_requested',
    });

    const stopped = await uploadAPI.stopAndDeleteBatch(7);
    expect(stopped.status).toBe('stopped');
    expect(stopped.result?.deletion?.deleted_count).toBe(1);
    expect(stopped.region_breakdown[0].status).toBe('pending');
    await expect(uploadAPI.deleteBatch(7)).rejects.toThrow('ניתן למחוק סטודנטים רק לאחר שההעלאה הסתיימה או נעצרה');
  });
});
