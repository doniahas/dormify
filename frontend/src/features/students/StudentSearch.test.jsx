import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import StudentSearch from './StudentSearch';
import { studentsAPI } from './api';
import { createDeferred } from '../../shared/test/deferred';

vi.mock('./api', () => ({
  studentsAPI: { getStudents: vi.fn(), getAll: vi.fn() },
}));

beforeEach(() => {
  vi.useFakeTimers();
  studentsAPI.getStudents.mockReset().mockResolvedValue([]);
  studentsAPI.getAll.mockReset().mockResolvedValue([]);
});

afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

async function search(term) {
  fireEvent.change(screen.getByRole('textbox'), { target: { value: term } });
  await act(async () => { await vi.advanceTimersByTimeAsync(300); });
}

describe('StudentSearch requests', () => {
  it('sends the trimmed typed term through getStudents with a signal', async () => {
    render(<StudentSearch language="en" onPick={vi.fn()} />);
    await search(' Ada ');
    expect(studentsAPI.getStudents).toHaveBeenCalledWith(
      { search: 'Ada' },
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(studentsAPI.getAll).not.toHaveBeenCalled();
  });

  it('keeps newer results when an older request resolves later and aborts on cleanup', async () => {
    const older = createDeferred();
    const newer = createDeferred();
    // Both boundary methods return the same controlled requests so the red
    // phase can expose the race independently of the method-name defect.
    for (const method of [studentsAPI.getStudents, studentsAPI.getAll]) {
      method.mockImplementationOnce(() => older.promise)
        .mockImplementationOnce(() => newer.promise);
    }
    const { unmount } = render(<StudentSearch language="en" onPick={vi.fn()} />);
    await search('Ada');
    await search('Grace');
    await act(async () => { newer.resolve({ results: [{ id: 2, full_name: 'Grace Hopper' }] }); });
    expect(screen.getByText('Grace Hopper')).toBeInTheDocument();
    await act(async () => { older.resolve([{ id: 1, full_name: 'Ada Lovelace' }]); });
    expect(screen.getByText('Grace Hopper')).toBeInTheDocument();
    expect(screen.queryByText('Ada Lovelace')).not.toBeInTheDocument();
    const calls = studentsAPI.getStudents.mock.calls;
    expect(calls[0][1].signal.aborted).toBe(true);
    expect(calls[1][1].signal.aborted).toBe(false);
    unmount();
    expect(calls[1][1].signal.aborted).toBe(true);
  });
});
