import { useState } from 'react'
import { FolderOpen, Loader2, ShieldCheck } from 'lucide-react'

import { Badge } from '@/design/shadcn/ui/badge'
import { Button } from '@/design/shadcn/ui/button'
import type {
  ExactServerMaterial,
  LocalSourceConnectAuthorizeInput,
  LocalSourceConnectPreviewInput,
} from '@/api/personalJourneyApi'

/**
 * J3 Connect: the owner names a folder and sees exactly what ACE would read
 * before anything is read.
 *
 * The order here is the product promise, not a UI detail. Previewing is lexical
 * and side-effect free; the first read happens only after the owner has seen the
 * exact scope and said yes. Editing the folder withdraws the previewed scope, so
 * consent can never be given for something other than what was shown.
 */

/** The mapped kinds the Personal pack ships, in the order an owner meets them. */
const DEFAULT_SCOPES: ReadonlyArray<{ readonly mapping_id: string; readonly include: readonly string[] }> = [
  { mapping_id: 'local_markdown_note', include: ['notes/*.md'] },
  { mapping_id: 'local_pdf_page', include: ['*.pdf'] },
  { mapping_id: 'local_csv_row', include: ['*.csv'] },
  { mapping_id: 'local_json_pointer', include: ['*.json'] },
]

function reason(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

export function ConnectLocalSources({
  profileId,
  profileDigest,
  sourceGroupId,
  scopes = DEFAULT_SCOPES,
  onPreview,
  onAuthorize,
  onAuthorized,
}: {
  readonly profileId: string
  readonly profileDigest: string
  readonly sourceGroupId: string
  readonly scopes?: ReadonlyArray<{ readonly mapping_id: string; readonly include: readonly string[] }>
  readonly onPreview: (input: LocalSourceConnectPreviewInput) => Promise<ExactServerMaterial>
  readonly onAuthorize: (input: LocalSourceConnectAuthorizeInput) => Promise<ExactServerMaterial>
  readonly onAuthorized?: (result: ExactServerMaterial) => void
}) {
  const [folder, setFolder] = useState('')
  const [preview, setPreview] = useState<ExactServerMaterial | null>(null)
  const [busy, setBusy] = useState<'preview' | 'authorize' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [captures, setCaptures] = useState<readonly ExactServerMaterial[] | null>(null)

  // Changing the folder withdraws the scope the owner was shown. Consent must
  // never carry over to material they have not seen.
  function editFolder(value: string) {
    setFolder(value)
    setPreview(null)
    setCaptures(null)
    setError(null)
  }

  async function showScope() {
    setBusy('preview')
    setError(null)
    try {
      setPreview(
        await onPreview({
          profile_id: profileId,
          profile_digest: profileDigest,
          source_group_id: sourceGroupId,
          authorized_root: folder,
          mapping_scopes: scopes,
          exclude: [],
        }),
      )
    } catch (caught) {
      setError(reason(caught, 'ACE could not preview this folder.'))
    } finally {
      setBusy(null)
    }
  }

  async function allowRead() {
    if (preview === null) return
    setBusy('authorize')
    setError(null)
    try {
      const result = await onAuthorize({
        preview,
        authorized: true,
        authorized_at: new Date().toISOString(),
      })
      setCaptures((result.captures as readonly ExactServerMaterial[]) ?? [])
      onAuthorized?.(result)
    } catch (caught) {
      setError(reason(caught, 'ACE could not read this folder.'))
    } finally {
      setBusy(null)
    }
  }

  const mappingScopes = (preview?.mapping_scopes as ReadonlyArray<Record<string, unknown>>) ?? []

  return (
    <section className="space-y-4">
      <div className="space-y-2">
        <label className="text-sm font-medium" htmlFor="connect-folder">
          Which folder should ACE read?
        </label>
        <div className="flex gap-2">
          <input
            id="connect-folder"
            className="flex-1 rounded-md border px-3 py-2 text-sm"
            placeholder="/Users/you/notes"
            value={folder}
            onChange={(event) => editFolder(event.target.value)}
          />
          <Button disabled={folder.trim() === '' || busy !== null} onClick={showScope}>
            {busy === 'preview' ? <Loader2 className="size-4 animate-spin" /> : <FolderOpen className="size-4" />}
            Show me what ACE would read
          </Button>
        </div>
        <p className="text-muted-foreground text-xs">
          Nothing is read until you have seen the exact scope below and allowed it.
        </p>
      </div>

      {error !== null && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}

      {preview !== null && (
        <div className="space-y-3 rounded-lg border p-4">
          <div className="flex flex-wrap items-center gap-2">
            <ShieldCheck className="size-4" />
            <Badge variant="secondary">Read-only</Badge>
            <Badge variant="secondary">No network</Badge>
            <Badge variant="secondary">Nothing is written</Badge>
          </div>
          <div className="text-sm">
            <span className="text-muted-foreground">Folder: </span>
            <span className="font-mono">{String(preview.authorized_root ?? folder)}</span>
          </div>
          <ul className="space-y-1 text-sm">
            {mappingScopes.map((scope) => (
              <li key={String(scope.mapping_id)} className="font-mono text-xs">
                {((scope.include as readonly string[]) ?? []).join(', ')}
              </li>
            ))}
          </ul>
          {captures === null && (
            <Button disabled={busy !== null} onClick={allowRead}>
              {busy === 'authorize' ? <Loader2 className="size-4 animate-spin" /> : null}
              Allow ACE to read these files
            </Button>
          )}
        </div>
      )}

      {captures !== null && (
        <p className="text-sm">
          ACE read {captures.length} file{captures.length === 1 ? '' : 's'} from this folder.
        </p>
      )}
    </section>
  )
}
