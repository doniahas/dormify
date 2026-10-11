import React from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';

import Header from './Header';

// Header navigates through useNavigate, so the destination is observable
// only from the router. Rendering the current path as text keeps the
// assertion on behavior rather than on component internals.
function CurrentPath() {
  const { pathname } = useLocation();

  return <p>{`current path: ${pathname}`}</p>;
}

function renderHeader() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Header language="en" onLanguageToggle={() => {}} />
      <CurrentPath />
    </MemoryRouter>
  );
}

describe('Header quick search', () => {
  it.each([
    ['Transfer', '/transfers'],
    ['Staff', '/users'],
  ])('navigates from %s search to %s', async (term, destination) => {
    const user = userEvent.setup();
    renderHeader();
    await user.type(screen.getByRole('textbox'), term);
    await user.keyboard('{Enter}');
    expect(screen.getByText(`current path: ${destination}`)).toBeInTheDocument();
  });

  it('navigates to the students page on Enter and clears the input', async () => {
    const user = userEvent.setup();

    renderHeader();

    expect(screen.getByText('current path: /dashboard')).toBeInTheDocument();

    const search = screen.getByRole('textbox');

    await user.type(search, 'Students');
    expect(search).toHaveValue('Students');

    await user.keyboard('{Enter}');

    expect(screen.getByText('current path: /students')).toBeInTheDocument();
    expect(search).toHaveValue('');
  });
});
