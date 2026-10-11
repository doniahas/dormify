import { afterEach, describe, expect, it } from 'vitest';
import MockAdapter from 'axios-mock-adapter';
import { api } from '../../shared/api/client';
import { whatIfAPI } from './api';

const mock = new MockAdapter(api, { onNoMatch: 'throwException' });
afterEach(() => mock.reset());

const postBody = (index = 0) => JSON.parse(mock.history.post[index].data);

describe('building inactivation', () => {
  it('simulates with the selected building ids and returns the scenario', async () => {
    const scenario = { success: true, summary: { affected: 4 }, affected_students: [{ id: 1 }] };
    mock.onPost('/api/what-if/building-inactivation/simulate/').reply(200, scenario);

    await expect(whatIfAPI.simulateBuildingInactivation([11, 12])).resolves.toEqual(scenario);
    expect(postBody()).toEqual({ building_ids: [11, 12] });
  });

  it('confirms with the default reason and the inactivation flag', async () => {
    mock.onPost('/api/what-if/building-inactivation/confirm/').reply(200, { success: true, created_request_ids: [3] });

    await expect(whatIfAPI.confirmBuildingInactivation([11])).resolves.toEqual({ success: true, created_request_ids: [3] });
    expect(postBody()).toEqual({ building_ids: [11], reason: 'Building inactivated', inactivate_buildings: true });

    await whatIfAPI.confirmBuildingInactivation([11], 'Renovation');
    expect(postBody(1).reason).toBe('Renovation');
  });
});

describe('availability change', () => {
  it('maps the camelCase input onto the backend fields with the defaults applied', async () => {
    mock.onPost('/api/what-if/availability/simulate/').reply(200, { success: true });
    mock.onPost('/api/what-if/availability/confirm/').reply(200, { success: true });

    await whatIfAPI.simulateAvailabilityChange({ targetType: 'apartment', targetIds: [5, 6] });
    await whatIfAPI.confirmAvailabilityChange({ targetType: 'room', targetIds: [9], action: 'reactivate' });

    expect(postBody(0)).toEqual({ target_type: 'apartment', target_ids: [5, 6], action: 'inactivate' });
    expect(postBody(1)).toEqual({ target_type: 'room', target_ids: [9], action: 'reactivate', reason: 'Availability changed' });
  });

  it('rejects with the backend explanation when a scenario is refused', async () => {
    mock.onPost('/api/what-if/availability/simulate/').reply(400, {
      error: 'No active targets selected', error_type: 'validation',
    });

    await expect(
      whatIfAPI.simulateAvailabilityChange({ targetType: 'building', targetIds: [] })
    ).rejects.toThrow('error: No active targets selected; error_type: validation');
  });
});
