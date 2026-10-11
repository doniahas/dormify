import React, { StrictMode } from 'react';
import { expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import FiltersDrawer from './FiltersDrawer';

const options = { is_central_admin: true, regions: [], dorm_types: [], buildings: [], apartments: [], rooms: [] };

it('handles options arriving, disappearing and returning while preserving the filter contract', async () => {
  const user = userEvent.setup();
  const changed = vi.fn();
  const close = vi.fn();
  const view = (filterOptions, isOpen = true) => (
    <StrictMode>
      <FiltersDrawer isOpen={isOpen} onClose={close} filters={{}} onFiltersChange={changed} filterOptions={filterOptions} totalCount={12} language="en" />
    </StrictMode>
  );
  const { rerender } = render(view(null));
  expect(screen.queryByText('Filter Students')).not.toBeInTheDocument();
  rerender(view(options));
  expect(screen.getByText('Filter Students')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Man', exact: true }));
  expect(changed).toHaveBeenLastCalledWith({ genders: ['male'] });
  rerender(view(null));
  expect(screen.queryByText('Filter Students')).not.toBeInTheDocument();
  rerender(view(options, false));
  rerender(view(options));
  await user.click(screen.getByRole('button', { name: 'Woman', exact: true }));
  expect(changed).toHaveBeenLastCalledWith({ genders: ['female'] });
});

it('clears dependent location filters when a region changes and keeps unrelated filters', async () => {
  const user = userEvent.setup();
  const changed = vi.fn();
  const filters = { genders: ['male'], dormTypes: [2], buildings: [3], apartments: [4], rooms: [5] };
  render(<FiltersDrawer isOpen onClose={vi.fn()} filters={filters} onFiltersChange={changed}
    filterOptions={{ ...options, regions: [{ id: 1, name: 'North' }] }} language="en" />);
  await user.click(screen.getByText('Select region'));
  await user.click(screen.getByText('North'));
  expect(changed).toHaveBeenCalledWith({ genders: ['male'], regions: [1], dormTypes: [], buildings: [], apartments: [], rooms: [] });
});

it('updates available dorm types with region filters and preserves the close action', () => {
  const close = vi.fn();
  const filterOptions = { ...options, dorm_types: [
    { id: 2, name: 'North dorm', region_id: 1 },
    { id: 3, name: 'South dorm', region_id: 2 },
  ] };
  const view = (regions) => <FiltersDrawer isOpen onClose={close} filters={{ regions }}
    onFiltersChange={vi.fn()} filterOptions={filterOptions} totalCount={12} language="en" />;
  const { rerender } = render(view(['1']));
  fireEvent.focus(screen.getByPlaceholderText('Search or select dorm type...'));
  expect(screen.getByText('North dorm')).toBeInTheDocument();
  expect(screen.queryByText('South dorm')).not.toBeInTheDocument();
  rerender(view([2]));
  expect(screen.queryByText('North dorm')).not.toBeInTheDocument();
  expect(screen.getByText('South dorm')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Show 12 students' }));
  expect(close).toHaveBeenCalledOnce();
});
