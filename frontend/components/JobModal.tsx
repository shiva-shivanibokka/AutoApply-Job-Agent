"use client"

import { useEffect, useState, useCallback, useRef } from "react"
import type { Job } from "@/lib/types"
import { fetchJobDescription, updateJobStatus } from "@/lib/api"
import { PIPELINE_STAGES, STATUS_META } from "@/lib/status"
import {
  XIcon, ExternalLinkIcon, MapPinIcon, BuildingIcon,
  LoaderIcon, RefreshCwIcon, MailIcon, LinkedinIcon, CopyIcon, CheckIcon,
} from "lucide-react"

const BADGE_COLORS: Record<string, { bg: string; color: string }> = {
  remote:      { bg: "#dcfce7", color: "#15803d" },
  hybrid:      { bg: "#dbeafe", color: "#1d4ed8" },
  onsite:      { bg: "#f3f4f6", color: "#374151" },
  "full-time": { bg: "#eef1fb", color: "#5b5ef4" },
  "part-time": { bg: "#fef3c7", color: "#92400e" },
  contract:    { bg: "#fce7f3", color: "#9d174d" },
  internship:  { bg: "#ede9fe", color: "#6d28d9" },
}

const SOURCE_STYLES: Record<string, { bg: string; color: string }> = {
  greenhouse: { bg: "#dcfce7", color: "#15803d" },
  lever:      { bg: "#dbeafe", color: "#1d4ed8" },
  ashby:      { bg: "#ede9fe", color: "#6d28d9" },
  adzuna:     { bg: "#fef3c7", color: "#92400e" },
}

function WorkplaceBadge({ label }: { label: string }) {
  const s = BADGE_COLORS[label.toLowerCase()] ?? { bg: "#f3f4f6", color: "#6b7280" }
  return (
    <span style={{
      fontSize: 12, fontWeight: 700, padding: "2px 9px", borderRadius: 5,
      background: s.bg, color: s.color,
    }}>
      {label.charAt(0).toUpperCase() + label.slice(1)}
    </span>
  )
}

function timeAgo(iso: string): string {
  if (!iso) return ""
  const diff = Date.now() - new Date(iso).getTime()
  if (isNaN(diff)) return ""
  const days   = Math.floor(diff / 86400000)
  const weeks  = Math.floor(days / 7)
  const months = Math.floor(days / 30)
  if (days < 1)    return "today"
  if (days < 7)    return `${days}d ago`
  if (days < 30)   return `${weeks}w ago`
  if (months < 12) return `${months}mo ago`
  return new Date(iso).toLocaleDateString("en-US", { month: "short", year: "numeric" })
}

function buildLinkedInUrl(company: string): string {
  const keywords = encodeURIComponent(`recruiter "${company}"`)
  return `https://www.linkedin.com/search/results/people/?keywords=${keywords}&origin=GLOBAL_SEARCH_HEADER`
}

function buildEmailTemplate(company: string, title: string): string {
  return `Subject: Interested in the ${title} role at ${company}

Hi [Name],

I came across the ${title} opening at ${company} and wanted to reach out directly. I'm genuinely excited about the work your team is doing and believe my background is a strong fit for this role.

I'd love to connect briefly if you have a few minutes — happy to share more about my experience or answer any questions you might have.

[Your name]
[LinkedIn / Portfolio]`
}

interface Props {
  job:            Job
  onClose:        () => void
  onStatusChange: (status: Job["status"]) => void
}

type Tab = "description" | "contacts"

export default function JobModal({ job, onClose, onStatusChange }: Props) {
  const [desc, setDesc]       = useState(job.description || "")
  const [loading, setLoading] = useState(false)
  const [status, setStatus]   = useState<Job["status"]>(job.status)
  const [tab, setTab]         = useState<Tab>("description")
  const [copied, setCopied]   = useState(false)
  const [copyFailed, setCopyFailed] = useState(false)
  const hasFetched            = useRef(false)
  const src = SOURCE_STYLES[job.source] ?? { bg: "#f3f4f6", color: "#6b7280" }

  // Auto-fetch JD when modal opens if not already available.
  // hasFetched ref prevents the stale-closure re-fetch loop that would occur
  // if desc were in the dependency array.
  const fetchDesc = useCallback(async (force = false) => {
    if (!force && hasFetched.current) return
    hasFetched.current = true
    setLoading(true)
    try {
      const res = await fetchJobDescription(job.id)
      if (res.description) setDesc(res.description)
    } catch {
      // silent — show fallback message
    } finally {
      setLoading(false)
    }
  }, [job.id]) // desc intentionally omitted — tracked via hasFetched ref

  useEffect(() => {
    hasFetched.current = false
    fetchDesc()
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [job.id, onClose])

  async function handleStatusSelect(next: Job["status"]) {
    const prev = status
    setStatus(next)  // optimistic
    try {
      await updateJobStatus(job.id, next)
      onStatusChange(next)
      if (next === "dismissed") onClose()
    } catch {
      setStatus(prev)  // revert on network error
    }
  }

  async function handleCopyEmail() {
    // navigator.clipboard is undefined outside a secure context and can reject
    // when permission is denied. Unguarded, that threw an unhandled rejection and
    // left the button looking dead — no copy, no confirmation, no error.
    try {
      await navigator.clipboard.writeText(buildEmailTemplate(job.company, job.title))
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopyFailed(true)
      setTimeout(() => setCopyFailed(false), 2500)
    }
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 100,
        background: "rgba(15,17,30,0.45)",
        backdropFilter: "blur(3px)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: "24px 16px",
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="modal-in"
        style={{
          background: "var(--surface)",
          borderRadius: 18,
          width: "100%",
          maxWidth: 680,
          maxHeight: "88vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 24px 64px rgba(0,0,0,0.18)",
          border: "1px solid var(--border)",
          overflow: "hidden",
        }}
      >
        <div style={{
          padding: "20px 24px 16px",
          borderBottom: "1px solid var(--border)",
          flexShrink: 0,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
            <div style={{ flex: 1 }}>
              <span style={{
                fontSize: 11, fontWeight: 700, padding: "2px 8px",
                borderRadius: 6, background: src.bg, color: src.color,
                display: "inline-block", marginBottom: 8,
              }}>
                {job.source.charAt(0).toUpperCase() + job.source.slice(1)}
              </span>

              <h2 style={{ fontSize: 20, fontWeight: 800, lineHeight: 1.25, color: "var(--text)", marginBottom: 6 }}>
                {job.title}
              </h2>

              <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
                <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 13, color: "var(--muted)" }}>
                  <BuildingIcon size={13} color="var(--accent)" /> {job.company}
                </span>
                {job.location && (
                  <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 13, color: "var(--muted)" }}>
                    <MapPinIcon size={13} /> {job.location}
                  </span>
                )}
                {job.workplace && <WorkplaceBadge label={job.workplace} />}
                {job.job_type  && <WorkplaceBadge label={job.job_type}  />}
                {job.posted_at && (
                  <span style={{ fontSize: 13, color: "var(--muted)" }}>
                    Posted {timeAgo(job.posted_at)}
                  </span>
                )}
                {job.match_score > 0 && (
                  <span style={{
                    fontSize: 12, fontWeight: 700, padding: "2px 9px", borderRadius: 5,
                    background: "#eef1fb", color: "var(--accent)",
                  }}>
                    Match {Math.round(job.match_score * 100)}%
                  </span>
                )}
              </div>
            </div>

            <button onClick={onClose} style={{
              background: "var(--surface2)", border: "1px solid var(--border)",
              borderRadius: 8, padding: 6, cursor: "pointer",
              display: "flex", alignItems: "center", color: "var(--muted)",
              flexShrink: 0,
            }}>
              <XIcon size={16} />
            </button>
          </div>

          {job.required_skills.length > 0 && (
            <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 12 }}>
              {job.required_skills.slice(0, 10).map(s => (
                <span key={s} style={{
                  fontSize: 11, padding: "2px 8px", borderRadius: 4,
                  background: "var(--surface2)", color: "var(--muted)",
                  border: "1px solid var(--border)", fontWeight: 500,
                }}>
                  {s}
                </span>
              ))}
            </div>
          )}

          <div style={{ display: "flex", gap: 8, marginTop: 14 }}>
            <a
              href={job.url} target="_blank" rel="noreferrer"
              onClick={e => e.stopPropagation()}
              style={{
                display: "flex", alignItems: "center", gap: 7,
                padding: "9px 20px", borderRadius: 10, border: "none",
                background: "var(--accent)", color: "#fff",
                fontWeight: 700, fontSize: 13, textDecoration: "none",
                transition: "background 0.15s",
              }}
              onMouseEnter={e => (e.currentTarget.style.background = "var(--accent-h)")}
              onMouseLeave={e => (e.currentTarget.style.background = "var(--accent)")}
            >
              <ExternalLinkIcon size={14} /> Apply Now
            </a>

            <select
              value={status === "dismissed" ? "new" : status}
              onChange={e => handleStatusSelect(e.target.value as Job["status"])}
              onClick={e => e.stopPropagation()}
              title="Track this job in your pipeline"
              style={{
                padding: "9px 14px", borderRadius: 10,
                border: `1.5px solid ${status !== "new" && status !== "dismissed" ? "var(--accent)" : "var(--border)"}`,
                background: status !== "new" && status !== "dismissed" ? STATUS_META[status].bg : "var(--surface)",
                color: status !== "new" && status !== "dismissed" ? STATUS_META[status].color : "var(--muted)",
                fontWeight: 600, fontSize: 13, cursor: "pointer",
              }}
            >
              <option value="new">＋ Track</option>
              {PIPELINE_STAGES.map(s => (
                <option key={s} value={s}>{STATUS_META[s].label}</option>
              ))}
            </select>

            <button onClick={() => handleStatusSelect("dismissed")} style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "9px 16px", borderRadius: 10,
              border: "1.5px solid var(--border)",
              background: "var(--surface)", color: "var(--muted)",
              fontWeight: 600, fontSize: 13, cursor: "pointer",
              marginLeft: "auto",
            }}>
              <XIcon size={13} /> Not interested
            </button>
          </div>
        </div>

        <div style={{
          display: "flex", borderBottom: "1px solid var(--border)",
          flexShrink: 0, padding: "0 24px",
        }}>
          {(["description", "contacts"] as Tab[]).map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              padding: "12px 4px", marginRight: 20,
              background: "none", border: "none", cursor: "pointer",
              fontSize: 13, fontWeight: tab === t ? 700 : 500,
              color: tab === t ? "var(--accent)" : "var(--muted)",
              borderBottom: tab === t ? "2px solid var(--accent)" : "2px solid transparent",
              transition: "all 0.15s",
            }}>
              {t === "description" ? "Job Description" : "Find Contacts"}
            </button>
          ))}
        </div>

        <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>
          {tab === "description" && (
            <>
              <div style={{
                display: "flex", alignItems: "center",
                justifyContent: "space-between", marginBottom: 14,
              }}>
                <div style={{ fontWeight: 700, fontSize: 15, color: "var(--text)" }}>
                  Job Description
                </div>
                <button
                  onClick={() => fetchDesc(true)}
                  disabled={loading}
                  style={{
                    display: "flex", alignItems: "center", gap: 5,
                    background: "none", border: "none", cursor: loading ? "not-allowed" : "pointer",
                    color: "var(--muted)", fontSize: 12, padding: "4px 8px",
                    borderRadius: 6,
                  }}
                >
                  {loading
                    ? <><LoaderIcon size={12} className="spin" /> Fetching…</>
                    : <><RefreshCwIcon size={12} /> Refresh</>}
                </button>
              </div>

              {loading && !desc && (
                <div style={{
                  display: "flex", flexDirection: "column", alignItems: "center",
                  gap: 10, padding: "40px 0", color: "var(--muted)",
                }}>
                  <LoaderIcon size={24} className="spin" color="var(--accent)" />
                  <span style={{ fontSize: 13 }}>Fetching job description…</span>
                </div>
              )}

              {!loading && !desc && (
                <div style={{
                  padding: "32px 0", textAlign: "center",
                  color: "var(--muted)", fontSize: 13,
                }}>
                  No description available for this posting.
                  <br />
                  <a href={job.url} target="_blank" rel="noreferrer"
                    style={{ color: "var(--accent)", marginTop: 8, display: "inline-block" }}>
                    View on company site
                  </a>
                </div>
              )}

              {desc && (
                <div style={{
                  fontSize: 14, lineHeight: 1.8, color: "var(--text)",
                  whiteSpace: "pre-wrap",
                }}>
                  {desc}
                </div>
              )}
            </>
          )}

          {tab === "contacts" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

              <div style={{
                padding: 16, borderRadius: 12,
                background: "var(--surface2)", border: "1px solid var(--border)",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <LinkedinIcon size={16} color="#0a66c2" />
                  <span style={{ fontWeight: 700, fontSize: 14, color: "var(--text)" }}>
                    Find recruiters on LinkedIn
                  </span>
                </div>
                <p style={{ fontSize: 13, color: "var(--muted)", marginBottom: 12, lineHeight: 1.6 }}>
                  Search for recruiters and HR people at {job.company} on LinkedIn. Connect with them or send a message referencing the {job.title} role.
                </p>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <a
                    href={buildLinkedInUrl(job.company)}
                    target="_blank" rel="noreferrer"
                    style={{
                      display: "flex", alignItems: "center", gap: 6,
                      padding: "8px 16px", borderRadius: 8,
                      background: "#0a66c2", color: "#fff",
                      fontSize: 13, fontWeight: 600, textDecoration: "none",
                    }}
                  >
                    <LinkedinIcon size={13} /> Search recruiters at {job.company}
                  </a>
                  <a
                    href={`https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(`hiring manager ${job.title} ${job.company}`)}`}
                    target="_blank" rel="noreferrer"
                    style={{
                      display: "flex", alignItems: "center", gap: 6,
                      padding: "8px 16px", borderRadius: 8,
                      border: "1.5px solid #0a66c2", color: "#0a66c2",
                      fontSize: 13, fontWeight: 600, textDecoration: "none",
                      background: "none",
                    }}
                  >
                    <LinkedinIcon size={13} /> Search hiring managers
                  </a>
                </div>
              </div>

              <div style={{
                padding: 16, borderRadius: 12,
                background: "var(--surface2)", border: "1px solid var(--border)",
              }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <MailIcon size={16} color="var(--accent)" />
                    <span style={{ fontWeight: 700, fontSize: 14, color: "var(--text)" }}>
                      Cold email template
                    </span>
                  </div>
                  <button
                    onClick={handleCopyEmail}
                    style={{
                      display: "flex", alignItems: "center", gap: 5,
                      padding: "5px 12px", borderRadius: 6,
                      background: copyFailed ? "#fee2e2" : copied ? "#dcfce7" : "var(--surface)",
                      border: `1px solid ${copyFailed ? "#b91c1c" : copied ? "#16a34a" : "var(--border)"}`,
                      color: copyFailed ? "#b91c1c" : copied ? "#16a34a" : "var(--muted)",
                      fontSize: 12, fontWeight: 600, cursor: "pointer",
                      transition: "all 0.2s",
                    }}
                  >
                    {copyFailed
                      ? <><CopyIcon size={12} /> Copy failed — select the text</>
                      : copied
                        ? <><CheckIcon size={12} /> Copied</>
                        : <><CopyIcon size={12} /> Copy</>}
                  </button>
                </div>
                <p style={{ fontSize: 13, color: "var(--muted)", marginBottom: 12, lineHeight: 1.6 }}>
                  Once you find a recruiter's email, send this. Keep it short — recruiters get a lot of messages.
                </p>
                <pre style={{
                  fontSize: 12, lineHeight: 1.7, color: "var(--text)",
                  background: "var(--surface)", border: "1px solid var(--border)",
                  borderRadius: 8, padding: 14,
                  whiteSpace: "pre-wrap", fontFamily: "inherit",
                  margin: 0,
                }}>
                  {buildEmailTemplate(job.company, job.title)}
                </pre>
              </div>

              <div style={{
                padding: 14, borderRadius: 10,
                background: "#fffbeb", border: "1px solid #fde68a",
                fontSize: 12, color: "#92400e", lineHeight: 1.6,
              }}>
                <strong>Tip:</strong> On LinkedIn, filter your search by "1st" or "2nd" degree connections first — a warm introduction is far more effective than a cold message. Also check the company's About page on LinkedIn for their recruiting team.
              </div>

            </div>
          )}
        </div>
      </div>
    </div>
  )
}
