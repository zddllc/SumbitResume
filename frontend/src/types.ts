export type Contact = { name: string; email: string; phone: string; location: string; linkedin: string; website: string }
export type Experience = { company: string; title: string; location: string; start_date: string; end_date: string; bullets: string[] }
export type Education = { institution: string; degree: string; field: string; start_date: string; end_date: string; details: string[] }
export type Project = { name: string; url: string; bullets: string[] }
export type Certification = { name: string; issuer: string; date: string }
export type Language = { name: string; proficiency: string }
export type ResumeProfile = {
  contact: Contact; summary: string; skills: string[]; experience: Experience[]
  education: Education[]; projects: Project[]; certifications: Certification[]; languages: Language[]
}
export type User = { id?: string; name: string; email: string }
export type Session = { user: User | null; setup_required: boolean; csrf_token: string }
export type ResumeRecord = {
  id: string; draft?: ResumeProfile | null; confirmed?: ResumeProfile
  edit_token: string; draft_filename?: string; confirmed_at?: string; confirmed_hash?: string
}
export type Answer = 'unspecified' | 'yes' | 'no' | 'decline'
export type PersonalInfo = {
  work_authorization: string; needs_sponsorship: Answer; willing_to_relocate: Answer
  preferred_locations: string[]; notice_period: string; salary_expectation: string
  veteran_status: 'unspecified' | 'not_veteran' | 'veteran' | 'decline'; disability_status: Answer
}
export type Provider = 'deepseek' | 'azure_openai' | 'azure_deepseek' | 'openai'
export type LLMSettings = { provider: Provider; model: string; base_url: string; api_version: string; key_saved: boolean }
export type Credential = { id: string; site: string; label: string; username_hint: string }
export type TaskStatus = 'queued' | 'running' | 'cancelling' | 'succeeded' | 'failed' | 'cancelled' | 'interrupted'
export type Task = {
  id: string; kind: 'browser' | 'parse' | 'scan' | 'tailor'; status: TaskStatus; created_at: string
  processed: number; generated: number; cached: number; failed: number
  error?: string | null; errors: { job_id: string; message: string }[]
}
export type ApplicationInfo = { kind: 'external' | 'easy_apply' | 'unavailable'; url?: string | null; error?: string | null }
export type PdfArtifact = { file_id: string; sha256: string; profile_hash: string; size: number; created_at: string }
export type ResumeVersion = { id: string; created_at: string; llm: { model: string }; review_status: string; pdf?: PdfArtifact }
export type Job = {
  id: string; linkedin_id: string; url: string; title: string; company: string; location: string
  description?: string; application_kind?: ApplicationInfo['kind']; application_url?: string | null
  application_error?: string | null; tailored?: ResumeVersion | null; current_source?: boolean
}
export type TailoredResume = ResumeVersion & {
  job: Job & { description: string }; resume: ResumeProfile; source_resume: ResumeProfile
  edit_token: string; application: ApplicationInfo; pdf_ready: boolean; reviewed_at?: string
}
export type AppState = {
  user: User; resume: ResumeRecord | null; personal: PersonalInfo
  llm: Partial<LLMSettings> & { key_saved: boolean }; credentials: Credential[]; tasks: Task[]
}
export type JobPage = { items: Job[]; page: number; total: number }
export type JobDetail = { job: Job & { description: string }; versions: ResumeVersion[] }
export type Message = { text: string; kind: 'info' | 'success' | 'error' }
export type EditableEntry = Record<string, string | string[]>
export type FieldDefinition = { key: string; label: string; multiline?: boolean }
