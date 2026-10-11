import { afterEach, describe, expect, it } from 'vitest';
import MockAdapter from 'axios-mock-adapter';
import { api } from '../../shared/api/client';
import { studentsAPI } from './api';

const mock = new MockAdapter(api, { onNoMatch: 'throwException' });
afterEach(() => mock.reset());

const posted = () => mock.history.post.map(({ url, data }) => [url, JSON.parse(data)]);

describe('room assignment endpoints', () => {
  it('assigns and moves a student through their distinct endpoints', async () => {
    mock.onPost('/api/room-assignments/assign/').reply(200, { ok: true });
    mock.onPost('/api/room-assignments/move/').reply(200, { ok: true });

    await expect(studentsAPI.assignBed(2, 501, 9001)).resolves.toEqual({ ok: true });
    await expect(studentsAPI.reassignBed(1, 501, 9001)).resolves.toEqual({ ok: true });

    expect(posted()).toEqual([
      ['/api/room-assignments/assign/', { student_id: 2, room_id: 501, bed_id: 9001 }],
      ['/api/room-assignments/move/', { student_id: 1, room_id: 501, bed_id: 9001 }],
    ]);
  });

  it('omits the bed when only a room is given', async () => {
    mock.onPost('/api/room-assignments/assign/').reply(200, {});

    await studentsAPI.assignBed(2, 501);

    expect(posted()).toEqual([
      ['/api/room-assignments/assign/', { student_id: 2, room_id: 501 }],
    ]);
  });

  // No screen calls unassignBed today; this only pins the adapter contract.
  it('unassigns a student by id', async () => {
    mock.onPost('/api/room-assignments/unassign/').reply(200, {});

    await studentsAPI.unassignBed(1);

    expect(posted()).toEqual([
      ['/api/room-assignments/unassign/', { student_id: 1 }],
    ]);
  });

  it('rejects with the backend explanation when a placement is refused', async () => {
    mock.onPost('/api/room-assignments/assign/').reply(400, {
      non_field_errors: ['Bed 9001 is already occupied'],
    });

    await expect(studentsAPI.assignBed(2, 501, 9001)).rejects.toThrow(
      'Bed 9001 is already occupied'
    );
  });
});
