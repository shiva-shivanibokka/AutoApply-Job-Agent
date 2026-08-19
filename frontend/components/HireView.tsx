"use client"

import { useState, useCallback, useEffect, type ReactNode } from "react"
import type { Job } from "@/lib/types"
import { listJobs } from "@/lib/api"
import { matchesSponsorship, type SponsorshipFilter } from "@/lib/sponsorship"
import SearchBar from "./SearchBar"
import JobGrid from "./JobGrid"
import JobModal from "./JobModal"
import PipelineBoard from "./PipelineBoard"
import { BriefcaseIcon, SearchIcon, LayoutListIcon } from "lucide-react"

export type ExperienceLevel = "any" | "intern" | "newgrad" | "mid" | "senior" | "staff"
export type PostedWithin    = "any" | "7" | "14" | "30"
export type JobTypeFilter   = "any" | "full-time" | "part-time" | "contract" | "internship" | "remote" | "hybrid" | "onsite"

// Title signals checked first (higher confidence), then description year-range patterns.
const EXP_SIGNALS: Record<Exclude<ExperienceLevel, "any">, {
  title: string[]
  desc:  string[]
}> = {
  intern: {
    title: ["intern", "internship", "co-op", "coop", "placement", "werkstudent", "apprentice", "trainee"],
    desc:  ["internship program", "intern position", "summer internship", "intern role"],
  },
  newgrad: {
    title: ["junior", "jr.", "jr ", "associate", "entry level", "entry-level",
            "new grad", "new-grad", "graduate", "early career", "early-career",
            "level 1", "level i", " i ", "l1 "],
    desc:  ["0-2 year", "0 to 2 year", "1-2 year", "1 to 2 year",
            "less than 2 year", "no experience required", "recent graduate",
            "fresh graduate", "0+ year", "entry level", "new graduate",
            "bachelor.*recent", "degree required.*no experience"],
  },
  mid: {
    title: ["mid-level", "mid level", "midlevel", "intermediate",
            "level 2", "level ii", "level 3", "level iii", " ii ", " iii ", "l2 ", "l3 "],
    desc:  ["2\\+ year", "3\\+ year", "4\\+ year", "2-4 year", "2-5 year",
            "3-5 year", "3 to 5 year", "2 to 4 year", "2 to 5 year",
            "at least 2 year", "at least 3 year", "minimum 2 year", "minimum 3 year"],
  },
  senior: {
    title: ["senior", "sr\\.", "sr ", "level 4", "level iv", "level 5", "level v",
            " iv ", " v ", "l4 ", "l5 "],
    desc:  ["5\\+ year", "6\\+ year", "7\\+ year", "5-8 year", "5-7 year",
            "5 to 8 year", "6 to 8 year", "at least 5 year", "minimum 5 year",
            "minimum 6 year", "extensive experience"],
  },
  staff: {
    title: ["staff", "principal", " lead ", "tech lead", "director", "head of",
            "vp ", "vice president", "level 6", "level 7", "l6 ", "l7 ",
            "distinguished", "fellow"],
    desc:  ["8\\+ year", "9\\+ year", "10\\+ year", "8-12 year", "10 or more year",
            "decade.*experience", "at least 8 year", "minimum 8 year"],
  },
}

// Most senior first. A title carrying two signals — "Senior Software Engineer II",
// "Staff Engineer L5" — should read as the higher one; ascending order let the
// numeric level token win and filed both under "mid". Intern stays first because
// it is unambiguous and never co-occurs with a seniority word.
const LEVELS_BY_CONFIDENCE = ["intern", "staff", "senior", "mid", "newgrad"] as const

function classifyExperience(job: Job): Exclude<ExperienceLevel, "any"> | null {
  const title = ` ${job.title.toLowerCase()} `
  const desc  = (job.description || "").toLowerCase().slice(0, 3000)

  // Every title is checked before any description, which is what the comment on
  // EXP_SIGNALS always claimed. Interleaving them per level meant a junior
  // description out-voted a senior title.
  for (const level of LEVELS_BY_CONFIDENCE) {
    if (EXP_SIGNALS[level].title.some(kw => title.includes(kw))) return level
  }

  for (const level of LEVELS_BY_CONFIDENCE) {
    if (EXP_SIGNALS[level].desc.some(p => {
      try { return new RegExp(p).test(desc) } catch { return false }
    })) return level
  }

  return null
}

function matchesExperience(job: Job, level: ExperienceLevel): boolean {
  if (level === "any") return true
  return classifyExperience(job) === level
}

function matchesJobType(job: Job, filter: JobTypeFilter): boolean {
  if (filter === "any") return true
  if (filter === "remote" || filter === "hybrid" || filter === "onsite") {
    if (job.workplace) return job.workplace === filter
    const loc = job.location.toLowerCase()
    if (filter === "remote") return loc.includes("remote")
    if (filter === "hybrid") return loc.includes("hybrid")
    // Only classify as onsite if the location gives a positive signal — never assume
    if (filter === "onsite") return loc.length > 0 && !loc.includes("remote") && !loc.includes("hybrid")
  }
  if (job.job_type) return job.job_type === filter
  const title = job.title.toLowerCase()
  if (filter === "internship") return title.includes("intern")
  if (filter === "part-time")  return title.includes("part-time") || title.includes("part time")
  if (filter === "contract")   return title.includes("contract") || title.includes("consultant")
  if (filter === "full-time")  return !title.includes("intern") && !title.includes("part-time") && !title.includes("contract")
  return true
}

function matchesPostedWithin(job: Job, within: PostedWithin): boolean {
  if (within === "any") return true
  const date = job.posted_at || job.scraped_at
  if (!date) return true
  const days = (Date.now() - new Date(date).getTime()) / 86400000
  return days <= parseInt(within, 10)
}

export default function HireView() {
  const [jobs, setJobs]         = useState<Job[]>([])
  const [selected, setSelected] = useState<Job | null>(null)
  const [sort, setSort]         = useState<"newest" | "relevance">("newest")
  const [exp, setExp]           = useState<ExperienceLevel>("any")
  const [within, setWithin]     = useState<PostedWithin>("any")
  const [jobType, setJobType]   = useState<JobTypeFilter>("any")
  const [sponsor, setSponsor]   = useState<SponsorshipFilter>("any")
  const [searched, setSearched] = useState(false)
  const [view, setView]         = useState<"search" | "pipeline">("search")
  const [pipeline, setPipeline] = useState<Job[]>([])
  const [pipeLoading, setPipeLoading] = useState(false)

  const handleJobsFound = useCallback((found: Job[]) => {
    setJobs(found)
    setSearched(true)
  }, [])

  const loadPipeline = useCallback(async () => {
    setPipeLoading(true)
    try {
      const { jobs } = await listJobs("tracked")
      setPipeline(jobs)
    } catch {
      // leave whatever is there; error surfaces as empty/stale
    } finally {
      setPipeLoading(false)
    }
  }, [])

  // Refresh the pipeline from the DB each time the user opens that view.
  useEffect(() => {
    if (view === "pipeline") loadPipeline()
  }, [view, loadPipeline])

  const handleStatusChange = useCallback((jobId: string, status: Job["status"]) => {
    setJobs(prev => prev.map(j => j.id === jobId ? { ...j, status } : j))
    setPipeline(prev => {
      const tracked = status !== "new" && status !== "dismissed"
      if (!tracked) return prev.filter(j => j.id !== jobId)
      return prev.map(j => j.id === jobId ? { ...j, status } : j)
      // ponytail: a job newly tracked from search view appears on next pipeline
      // open (loadPipeline re-fetches); no need to splice the full object in here.
    })
    if (status === "dismissed") setSelected(null)
  }, [])

  const visible = jobs
    .filter(j => j.status !== "dismissed")
    .filter(j => matchesExperience(j, exp))
    .filter(j => matchesJobType(j, jobType))
    .filter(j => matchesPostedWithin(j, within))
    .filter(j => matchesSponsorship(j, sponsor))
    .sort((a, b) => {
      if (sort === "newest") {
        const da = a.posted_at || a.scraped_at
        const db = b.posted_at || b.scraped_at
        if (!da && !db) return 0
        if (!da) return 1
        if (!db) return -1
        return new Date(db).getTime() - new Date(da).getTime()
      }
      return b.match_score - a.match_score
    })

  const newCount = visible.filter(j => j.is_new).length

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      <header style={{
        background: "var(--surface)",
        borderBottom: "1px solid var(--border)",
        padding: "0 32px",
        height: 56,
        display: "flex",
        alignItems: "center",
        gap: 10,
        position: "sticky",
        top: 0,
        zIndex: 10,
        boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{
            background: "var(--accent)", borderRadius: 8,
            width: 28, height: 28,
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <BriefcaseIcon size={15} color="#fff" />
          </div>
          <span style={{ fontWeight: 800, fontSize: 17, letterSpacing: "-0.4px", color: "var(--accent)" }}>
            HireView
          </span>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{
            display: "flex", background: "var(--surface2)",
            border: "1px solid var(--border)", borderRadius: 10, padding: 3,
          }}>
            <ViewTab active={view === "search"} onClick={() => setView("search")}
              icon={<SearchIcon size={14} />} label="Search" />
            <ViewTab active={view === "pipeline"} onClick={() => setView("pipeline")}
              icon={<LayoutListIcon size={14} />}
              label={`Pipeline${pipeline.length ? ` (${pipeline.length})` : ""}`} />
          </div>
          {view === "search" && searched && jobs.length > 0 && (
            <span style={{
              fontSize: 13, color: "var(--muted)",
              background: "var(--surface2)", padding: "3px 10px",
              borderRadius: 20, border: "1px solid var(--border)",
            }}>
              {visible.length} jobs
              {newCount > 0 && (
                <span style={{ color: "#15803d", fontWeight: 700 }}> · {newCount} new</span>
              )}
            </span>
          )}
        </div>
      </header>

      {view === "search" && (
        <div style={{
          background: "var(--surface)",
          borderBottom: "1px solid var(--border)",
          padding: "20px 32px",
        }}>
          <SearchBar
            onJobsFound={handleJobsFound}
            sort={sort}
            onSortChange={setSort}
            exp={exp}
            onExpChange={setExp}
            jobType={jobType}
            onJobTypeChange={setJobType}
            within={within}
            onWithinChange={setWithin}
            sponsor={sponsor}
            onSponsorChange={setSponsor}
          />
        </div>
      )}

      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "28px 32px" }}>
        {view === "pipeline" ? (
          <PipelineBoard
            jobs={pipeline}
            loading={pipeLoading}
            onSelect={setSelected}
            onStatusChange={handleStatusChange}
          />
        ) : !searched ? (
          <EmptyState />
        ) : visible.length === 0 ? (
          <div style={{ textAlign: "center", color: "var(--muted)", padding: "60px 0", fontSize: 15 }}>
            No jobs found. Try different keywords.
          </div>
        ) : (
          <JobGrid
            jobs={visible}
            onSelect={setSelected}
            onDismiss={(id) => handleStatusChange(id, "dismissed")}
          />
        )}
      </div>

      {selected && (
        <JobModal
          job={selected}
          onClose={() => setSelected(null)}
          onStatusChange={(status) => handleStatusChange(selected.id, status)}
        />
      )}
    </div>
  )
}

function ViewTab({ active, onClick, icon, label }: {
  active: boolean
  onClick: () => void
  icon: ReactNode
  label: string
}) {
  return (
    <button onClick={onClick} style={{
      display: "flex", alignItems: "center", gap: 6,
      padding: "5px 12px", borderRadius: 8, border: "none", cursor: "pointer",
      background: active ? "var(--surface)" : "transparent",
      color: active ? "var(--accent)" : "var(--muted)",
      fontWeight: active ? 700 : 600, fontSize: 13,
      boxShadow: active ? "0 1px 3px rgba(0,0,0,0.08)" : "none",
      transition: "all 0.15s",
    }}>
      {icon} {label}
    </button>
  )
}

function EmptyState() {
  return (
    <div style={{ textAlign: "center", padding: "80px 0" }}>
      <div style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        width: 64, height: 64, borderRadius: 16,
        background: "linear-gradient(135deg, #eef1fb, #e0e4ff)",
        marginBottom: 16,
      }}>
        <BriefcaseIcon size={28} color="var(--accent)" strokeWidth={1.5} />
      </div>
      <div style={{ fontSize: 18, fontWeight: 700, color: "var(--text)", marginBottom: 6 }}>
        Find your next role
      </div>
      <div style={{ fontSize: 14, color: "var(--muted)" }}>
        Search across Greenhouse, Lever, and Ashby — hundreds of companies at once
      </div>
    </div>
  )
}
