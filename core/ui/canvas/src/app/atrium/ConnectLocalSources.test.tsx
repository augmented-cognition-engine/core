import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { PersonalJourneyApiError } from '@/api/personalJourneyApi'
import { ConnectLocalSources } from './ConnectLocalSources'

const preview = {
  contract: 'ace.application.local-source-connect-preview/v1alpha1',
  preview_id: 'local_source_connect_preview:abc',
  acquisition_mode: 'local',
  read_only: true,
  network_capture_performed: false,
  write_access_requested: false,
  reusable_authority: false,
  authorized_root: '/Users/owner/notes',
  mapping_scopes: [
    { mapping_id: 'local_markdown_note', include: ['notes/*.md'], source_type_ref: 'markdown.note' },
    { mapping_id: 'local_pdf_page', include: ['*.pdf'], source_type_ref: 'pdf.page' },
  ],
}

function setup(overrides: Partial<Parameters<typeof ConnectLocalSources>[0]> = {}) {
  const onPreview = vi.fn().mockResolvedValue(preview)
  const onAuthorize = vi.fn().mockResolvedValue({ captures: [{ relative_path: 'notes/vault.md' }] })
  const onAuthorized = vi.fn()
  render(
    <ConnectLocalSources
      profileId="intelligence_onboarding_profile:personal"
      profileDigest={`sha256:${'a'.repeat(64)}`}
      sourceGroupId="personal_local_sources"
      onPreview={onPreview}
      onAuthorize={onAuthorize}
      onAuthorized={onAuthorized}
      {...overrides}
    />,
  )
  return { onPreview, onAuthorize, onAuthorized }
}

async function previewFolder() {
  fireEvent.change(screen.getByLabelText(/folder/i), { target: { value: '/Users/owner/notes' } })
  fireEvent.click(screen.getByRole('button', { name: /show me what ace would read/i }))
  await waitFor(() => screen.getByText(/read-only/i))
}

describe('naming a folder shows the exact scope before anything is read', () => {
  it('reads nothing until the owner has seen the scope and consented', async () => {
    const { onPreview, onAuthorize } = setup()

    expect(onPreview).not.toHaveBeenCalled()
    expect(onAuthorize).not.toHaveBeenCalled()

    await previewFolder()

    expect(onPreview).toHaveBeenCalledTimes(1)
    // Previewing is not consent: nothing has been read yet.
    expect(onAuthorize).not.toHaveBeenCalled()
  })

  it('discloses read-only, no-network and no-write before consent is offered', async () => {
    setup()
    await previewFolder()

    expect(screen.getByText('/Users/owner/notes')).toBeTruthy()
    expect(screen.getByText(/read-only/i)).toBeTruthy()
    expect(screen.getByText(/no network/i)).toBeTruthy()
    expect(screen.getByText(/nothing is written/i)).toBeTruthy()
    expect(screen.getByText(/notes\/\*\.md/)).toBeTruthy()
  })

  it('authorizes only the exact previewed scope the owner was shown', async () => {
    const { onAuthorize, onAuthorized } = setup()
    await previewFolder()

    fireEvent.click(screen.getByRole('button', { name: /allow ace to read these files/i }))

    await waitFor(() => expect(onAuthorize).toHaveBeenCalledTimes(1))
    const sent = onAuthorize.mock.calls[0][0]
    expect(sent.preview).toBe(preview)
    expect(sent.authorized).toBe(true)
    await waitFor(() => expect(onAuthorized).toHaveBeenCalledTimes(1))
  })

  it('re-editing the folder withdraws the previous scope so stale consent cannot be given', async () => {
    const { onAuthorize } = setup()
    await previewFolder()

    fireEvent.change(screen.getByLabelText(/folder/i), { target: { value: '/Users/owner/other' } })

    expect(screen.queryByRole('button', { name: /allow ace to read these files/i })).toBeNull()
    expect(onAuthorize).not.toHaveBeenCalled()
  })
})

describe('failures say what the server said', () => {
  it('shows the server’s exact reason rather than a generic message', async () => {
    setup({
      onPreview: vi.fn().mockRejectedValue(new PersonalJourneyApiError(404, 'That folder does not exist on this host.')),
    })

    fireEvent.change(screen.getByLabelText(/folder/i), { target: { value: '/nope' } })
    fireEvent.click(screen.getByRole('button', { name: /show me what ace would read/i }))

    await waitFor(() => screen.getByRole('alert'))
    expect(screen.getByRole('alert').textContent).toContain('That folder does not exist on this host.')
  })

  it('keeps the owner able to retry after a failed read', async () => {
    setup({
      onAuthorize: vi.fn().mockRejectedValue(new PersonalJourneyApiError(503, 'The source adapter is unavailable.')),
    })
    await previewFolder()

    fireEvent.click(screen.getByRole('button', { name: /allow ace to read these files/i }))

    await waitFor(() => screen.getByRole('alert'))
    expect(screen.getByRole('alert').textContent).toContain('The source adapter is unavailable.')
    expect(screen.getByRole('button', { name: /allow ace to read these files/i })).toBeTruthy()
  })
})
