import type { Metadata } from 'next';
import {
  BookOpen,
  CheckCircle2,
  Clock3,
  ExternalLink,
  Library,
  Radio,
  ScrollText,
} from 'lucide-react';
import { ListenButton } from './ListenButton';

export type ReporterPageConfig = {
  uid: string;
  slug: string;
  displayName: string;
  initials: string;
  description: string;
  // A reporter whose character also anchors a live station elsewhere (only
  // af.heart today — Torchy and Miriam have no station counterpart). This
  // is a distinct action from ListenButton below: that reads a lecture's
  // text aloud via browser speech synthesis, this navigates to a live
  // external stream. Keep them visually and functionally separate rather
  // than overloading one control with both meanings.
  externalStation?: { url: string; label: string };
};

export function reporterMetadata(config: ReporterPageConfig): Metadata {
  const url = `https://arc-codex.com/reporters/${config.slug}`;
  const title = `${config.displayName} | School of Chat Faculty | Arc Codex`;
  return {
    title: { absolute: title },
    description: config.description,
    alternates: { canonical: url },
    robots: 'index, follow',
    openGraph: {
      title,
      description: config.description,
      type: 'profile',
      url,
    },
  };
}

const FACULTY_API_BASE =
  process.env.FACULTY_DIRECTORY_INTERNAL_URL ?? 'http://127.0.0.1:8765';
const REQUEST_TIMEOUT_MS = 3500;

type FacultyProfile = {
  uid: string;
  identity: {
    displayName: string;
    givenName: string;
    synthetic: boolean;
  };
  institution: {
    title: string;
    school: string;
    department: string;
  };
  expertise: {
    primary: string[];
    secondary: string[];
  };
  teaching: {
    biography: string;
    style: string[];
  };
  personality: {
    voice: string;
  };
  avatar: {
    uri: string;
    alt: string;
  };
};

type LectureSummary = {
  lecture_id: string;
  professor_uid: string;
  title: string;
  subject: string;
  summary: string;
  language: string;
  audience: string;
  estimated_minutes: number;
  created_at: string;
  status: string;
};

type LectureSource = {
  source_id: string;
  source_type: string;
  title: string;
  author: string;
  url: string | null;
  citation: string;
  section_used: string;
  public_domain: boolean;
};

type Reading = {
  reading_id: string;
  title: string;
  author: string;
  library_url: string;
  recommended_section: string;
  estimated_minutes: number;
};

type WeeklyAssignment = {
  assignmentId: string;
  professorUid: string;
  lectureId: string;
  weekOf: string;
  title: string;
  subject: string;
  summary: string;
  audience: string;
  language: string;
  status: string;
  publishedAt: string;
  estimatedMinutes: number;
  lecture: {
    url: string;
    estimatedMinutes: number;
  };
  readings: Array<{
    readingId: string;
    title: string;
    author: string;
    recommendedSection: string;
    estimatedMinutes: number | null;
    libraryUrl: string | null;
  }>;
  quiz: {
    url: string;
    authority?: string;
    credentialDecision?: string;
    questionCount: number;
    passingThreshold: number;
  };
};

type QuizQuestion = {
  question_id: string;
  question_order: number;
  question: string;
  choices: string[];
  correct_answer: number;
  explanation: string;
};

type LectureDetails = LectureSummary & {
  lecture_text: string;
  spoken_text: string | null;
  updated_at: string;
  process_name: string;
  process_version: string;
  model_name: string | null;
  provenance: {
    generation_mode?: string;
    source_collection?: string;
    source_snapshot_date?: string;
    editorial_note?: string;
  };
  sources: LectureSource[];
  readings: Reading[];
  quiz_questions: QuizQuestion[];
  passing_threshold: number;
  audio_url?: string | null;
  audio?: { url?: string | null } | null;
  assessment_authority?: {
    assessment_id: string;
    authority_id: string;
    authority_url: string;
    issuance_mode: string;
    reporter_package_can_issue_credentials: boolean;
  } | null;
};

type LectureListResponse = {
  professorUid: string;
  count: number;
  lectures: LectureSummary[];
};

type AssignmentListResponse = {
  professorUid: string;
  count: number;
  assignments: WeeklyAssignment[];
};

type PageData = {
  profile: FacultyProfile;
  lectures: LectureSummary[];
  assignments: WeeklyAssignment[];
  currentLecture: LectureDetails | null;
  portraitDataUri: string | null;
  lectureServiceAvailable: boolean;
  assignmentServiceAvailable: boolean;
};

function internalUrl(path: string): string {
  const base = FACULTY_API_BASE.replace(/\/+$/, '');
  return `${base}/${path.replace(/^\/+/, '')}`;
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(internalUrl(path), {
    cache: 'no-store',
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    headers: { Accept: 'application/json' },
  });

  if (!response.ok) {
    throw new Error(`Faculty service returned HTTP ${response.status}`);
  }

  return (await response.json()) as T;
}

function isFacultyProfile(value: unknown, uid: string): value is FacultyProfile {
  if (!value || typeof value !== 'object') return false;
  const profile = value as Partial<FacultyProfile>;
  return Boolean(
    profile.uid === uid &&
      profile.identity?.displayName &&
      profile.institution?.title &&
      profile.expertise?.primary &&
      profile.teaching?.biography,
  );
}

function isLectureList(value: unknown): value is LectureListResponse {
  if (!value || typeof value !== 'object') return false;
  const list = value as Partial<LectureListResponse>;
  return Array.isArray(list.lectures);
}

function isAssignmentList(value: unknown, uid: string): value is AssignmentListResponse {
  if (!value || typeof value !== 'object') return false;
  const list = value as Partial<AssignmentListResponse>;
  return list.professorUid === uid && Array.isArray(list.assignments);
}

async function fetchPortraitDataUri(uri: string): Promise<string | null> {
  // The directory controls this path, but constrain it anyway: the profile
  // must never turn this server component into a general-purpose URL fetcher.
  if (!/^avatars\/[a-z0-9._-]+\.(?:jpe?g|png|webp)$/i.test(uri)) return null;

  try {
    const response = await fetch(internalUrl(uri), {
      cache: 'no-store',
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      headers: { Accept: 'image/avif,image/webp,image/png,image/jpeg' },
    });
    if (!response.ok) return null;

    const contentType = response.headers.get('content-type')?.split(';')[0] ?? '';
    if (!contentType.startsWith('image/')) return null;

    const bytes = await response.arrayBuffer();
    if (bytes.byteLength === 0 || bytes.byteLength > 2_000_000) return null;
    return `data:${contentType};base64,${Buffer.from(bytes).toString('base64')}`;
  } catch {
    return null;
  }
}

async function loadPageData(config: ReporterPageConfig): Promise<PageData | null> {
  try {
    const rawProfile = await fetchJson<unknown>(`api/faculty/${config.uid}`);
    if (!isFacultyProfile(rawProfile, config.uid)) throw new Error('Unexpected faculty schema');

    const [lectureResult, assignmentResult, portraitDataUri] = await Promise.all([
      fetchJson<unknown>(`api/faculty/${config.uid}/lectures`)
        .then((value) => (isLectureList(value) ? value.lectures : []))
        .then((lectures) => ({ lectures, available: true }))
        .catch(() => ({ lectures: [] as LectureSummary[], available: false })),
      fetchJson<unknown>(`api/faculty/${config.uid}/assignments`)
        .then((value) => (isAssignmentList(value, config.uid) ? value.assignments : []))
        .then((assignments) => ({ assignments, available: true }))
        .catch(() => ({ assignments: [] as WeeklyAssignment[], available: false })),
      fetchPortraitDataUri(rawProfile.avatar?.uri ?? ''),
    ]);

    let currentLecture: LectureDetails | null = null;
    const currentSummary = lectureResult.lectures[0];
    if (currentSummary?.lecture_id) {
      currentLecture = await fetchJson<LectureDetails>(
        `api/lectures/${encodeURIComponent(currentSummary.lecture_id)}`,
      ).catch(() => null);
    }

    return {
      profile: rawProfile,
      lectures: lectureResult.lectures,
      assignments: assignmentResult.assignments,
      currentLecture,
      portraitDataUri,
      lectureServiceAvailable: lectureResult.available,
      assignmentServiceAvailable: assignmentResult.available,
    };
  } catch {
    return null;
  }
}

function humanize(value: string): string {
  return value
    .split('-')
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function formatDate(value: string): string {
  const date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T12:00:00Z` : value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'America/Denver',
  }).format(date);
}

function publicLink(value: string | null | undefined): string | null {
  if (!value) return null;
  if (value.startsWith('/')) return value;

  try {
    const url = new URL(value);
    if (url.protocol !== 'https:') return null;
    return url.toString();
  } catch {
    return null;
  }
}

function lectureAudioLink(lecture: LectureDetails | null): string | null {
  if (!lecture) return null;
  return publicLink(lecture.audio_url ?? lecture.audio?.url);
}

function lectureBlocks(text: string): Array<{ kind: 'heading' | 'paragraph'; text: string }> {
  return text
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean)
    .map((block) => ({
      kind: /^[A-Z0-9][A-Z0-9 '&’:-]+$/.test(block) ? 'heading' : 'paragraph',
      text: block,
    }));
}

function unavailablePage(config: ReporterPageConfig) {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="mx-auto max-w-3xl px-4 py-16 sm:px-6 lg:px-8">
        <header className="space-y-4 border-b border-slate-800/60 py-12 text-center">
          <p className="font-sans text-[10px] uppercase tracking-[0.4em] text-slate-500">
            School of Chat · Synthetic Faculty
          </p>
          <h1 className="font-serif text-4xl font-semibold tracking-tight text-slate-50 sm:text-6xl">
            {config.displayName}
          </h1>
        </header>
        <section className="space-y-3 border-b border-slate-800/60 py-12 text-center">
          <h2 className="font-serif text-2xl text-slate-200">The reading room is briefly closed.</h2>
          <p className="mx-auto max-w-xl font-serif leading-relaxed text-slate-400">
            {config.displayName}&apos;s live faculty record is temporarily unavailable. The profile and lectures
            remain in the School of Chat Character Directory; please try this page again shortly.
          </p>
        </section>
      </main>
    </div>
  );
}

export async function ReporterProfilePage({ config }: { config: ReporterPageConfig }) {
  const data = await loadPageData(config);
  if (!data) return unavailablePage(config);

  const {
    profile,
    lectures,
    assignments,
    currentLecture,
    portraitDataUri,
    lectureServiceAvailable,
    assignmentServiceAvailable,
  } = data;
  const current = currentLecture ?? lectures[0] ?? null;
  const currentAssignment = assignments[0] ?? null;
  const audioUrl = lectureAudioLink(currentLecture);
  const preferredSecondary = profile.expertise.secondary.find((field) => /myth/i.test(field));
  const coachingAreas = profile.expertise.primary.length >= 4
    ? profile.expertise.primary.slice(0, 4)
    : Array.from(new Set([
        ...profile.expertise.primary,
        preferredSecondary ?? profile.expertise.secondary[0],
      ])).slice(0, 4);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <main className="mx-auto max-w-5xl px-4 py-12 sm:px-6 sm:py-16 lg:px-8">
        <header className="grid gap-10 border-b border-slate-800/60 py-10 md:grid-cols-[minmax(0,1fr)_17rem] md:items-center md:py-14">
          <div className="space-y-6">
            <div className="space-y-3">
              <p className="font-sans text-[10px] uppercase tracking-[0.4em] text-amber-300/80">
                School of Chat · Faculty
              </p>
              <h1 className="font-serif text-5xl font-semibold uppercase leading-[0.95] tracking-tight text-slate-50 sm:text-6xl lg:text-7xl">
                {profile.identity.displayName}
              </h1>
            </div>

            <div className="space-y-1 font-serif text-lg leading-relaxed text-slate-300">
              <p>{profile.institution.title}</p>
              <p className="text-slate-400">{profile.institution.school}</p>
            </div>

            <ul className="flex flex-wrap gap-x-5 gap-y-2 font-sans text-[10px] uppercase tracking-[0.22em] text-slate-400">
              {coachingAreas.map((field) => <li key={field}>{field}</li>)}
            </ul>

            <p className="font-sans text-[10px] uppercase tracking-[0.25em] text-slate-500">
              Synthetic Faculty · School of Chat
            </p>

            <div className="max-w-2xl space-y-3">
              <p className="font-serif text-lg leading-relaxed text-slate-200">
                {profile.teaching.biography}
              </p>
              <p className="font-serif italic leading-relaxed text-slate-400">
                {profile.personality.voice}
              </p>
            </div>

            {config.externalStation && (
              <a
                href={config.externalStation.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 border border-amber-300/50 px-4 py-2.5 font-sans text-[10px] uppercase tracking-[0.2em] text-amber-200 transition-colors hover:border-amber-200 ring-focus"
              >
                <Radio className="h-3.5 w-3.5" aria-hidden="true" /> {config.externalStation.label}
              </a>
            )}
          </div>

          <figure className="mx-auto w-full max-w-[17rem] md:mx-0">
            {portraitDataUri ? (
              // A data URI is intentional: the image is fetched by this server component,
              // so browsers never contact the private faculty service.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={portraitDataUri}
                alt={profile.avatar.alt || `Synthetic portrait of ${profile.identity.displayName}`}
                width={1254}
                height={1254}
                className="aspect-square w-full border border-slate-700/70 object-cover shadow-2xl shadow-black/40"
              />
            ) : (
              <div
                role="img"
                aria-label={`Portrait placeholder for ${profile.identity.displayName}`}
                className="flex aspect-square items-center justify-center border border-slate-700/70 bg-slate-900 font-serif text-5xl text-slate-500"
              >
                {config.initials}
              </div>
            )}
            <figcaption className="mt-3 font-sans text-[9px] uppercase tracking-[0.22em] text-slate-600">
              Synthetic character portrait
            </figcaption>
          </figure>
        </header>

        <section className="border-b border-slate-800/60 py-12" aria-labelledby="now-teaching">
          <div className="grid gap-8 md:grid-cols-[10rem_minmax(0,1fr)]">
            <h2 id="now-teaching" className="font-sans text-xs font-semibold uppercase tracking-[0.28em] text-amber-300/80">
              Now Teaching
            </h2>

            {current ? (
              <div className="space-y-6">
                <div className="space-y-3">
                  <h3 className="font-serif text-3xl font-semibold leading-tight text-slate-50 sm:text-4xl">
                    {current.title}
                  </h3>
                  <p className="font-serif text-lg text-slate-400">
                    {current.subject} · {humanize(current.audience)}
                  </p>
                  <p className="flex items-center gap-2 font-sans text-xs uppercase tracking-[0.18em] text-slate-500">
                    <Clock3 className="h-3.5 w-3.5" aria-hidden="true" />
                    {current.estimated_minutes} minute lecture
                  </p>
                </div>

                <p className="max-w-2xl font-serif leading-relaxed text-slate-300">{current.summary}</p>

                <nav className="flex flex-wrap gap-3" aria-label="Lecture actions">
                  {currentLecture?.lecture_text && (
                    <a href="#lecture" className="inline-flex items-center gap-2 border border-slate-700 px-4 py-2.5 font-sans text-[10px] uppercase tracking-[0.2em] text-slate-200 transition-colors hover:border-amber-300/60 hover:text-amber-200 ring-focus">
                      <BookOpen className="h-3.5 w-3.5" aria-hidden="true" /> Read Lecture
                    </a>
                  )}
                  {currentLecture?.quiz_questions?.length ? (
                    <a href={currentLecture.assessment_authority?.authority_url ?? '#quiz'} className="inline-flex items-center gap-2 border border-slate-700 px-4 py-2.5 font-sans text-[10px] uppercase tracking-[0.2em] text-slate-200 transition-colors hover:border-amber-300/60 hover:text-amber-200 ring-focus">
                      <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" /> Take Quiz
                    </a>
                  ) : null}
                  {currentLecture?.sources?.length ? (
                    <a href="#sources" className="inline-flex items-center gap-2 border border-slate-700 px-4 py-2.5 font-sans text-[10px] uppercase tracking-[0.2em] text-slate-200 transition-colors hover:border-amber-300/60 hover:text-amber-200 ring-focus">
                      <ScrollText className="h-3.5 w-3.5" aria-hidden="true" /> Sources
                    </a>
                  ) : null}
                  {audioUrl ? (
                    <a href={audioUrl} className="inline-flex items-center gap-2 border border-amber-300/50 px-4 py-2.5 font-sans text-[10px] uppercase tracking-[0.2em] text-amber-200 transition-colors hover:border-amber-200 ring-focus">
                      ▶ Listen
                    </a>
                  ) : currentLecture?.lecture_text ? (
                    <ListenButton
                      text={currentLecture.spoken_text ?? currentLecture.lecture_text}
                      label={currentLecture.title}
                    />
                  ) : null}
                </nav>
              </div>
            ) : (
              <p className="font-serif text-lg italic leading-relaxed text-slate-400">
                {lectureServiceAvailable
                  ? 'No lecture is on the reading stand today.'
                  : 'Today’s lecture is temporarily unavailable. Please check back shortly.'}
              </p>
            )}
          </div>
        </section>

        <section id="weekly-assignment" className="scroll-mt-8 border-b border-slate-800/60 py-12" aria-labelledby="weekly-assignment-title">
          <div className="grid gap-8 md:grid-cols-[10rem_minmax(0,1fr)]">
            <h2 id="weekly-assignment-title" className="font-sans text-xs font-semibold uppercase tracking-[0.28em] text-amber-300/80">
              This Week
            </h2>

            {currentAssignment ? (
              <div className="max-w-3xl space-y-6">
                <div className="space-y-2">
                  <p className="font-sans text-[10px] uppercase tracking-[0.22em] text-slate-500">
                    Week of {formatDate(currentAssignment.weekOf)} · about {currentAssignment.estimatedMinutes} minutes
                  </p>
                  <h3 className="font-serif text-3xl font-semibold leading-tight text-slate-50">
                    {currentAssignment.title}
                  </h3>
                  <p className="font-serif leading-relaxed text-slate-300">{currentAssignment.summary}</p>
                </div>

                <ol className="border-t border-slate-800/50">
                  <li className="grid gap-2 border-b border-slate-800/50 py-5 sm:grid-cols-[2rem_minmax(0,1fr)_auto] sm:items-start">
                    <span className="font-sans text-[10px] tracking-[0.2em] text-slate-600">01</span>
                    <div>
                      <p className="font-serif text-xl text-slate-100">Attend the lecture</p>
                      <p className="mt-1 font-serif text-sm text-slate-500">{currentAssignment.subject} · {humanize(currentAssignment.audience)}</p>
                    </div>
                    <a href="#lecture" className="font-sans text-[10px] uppercase tracking-[0.2em] text-amber-200 hover:text-amber-100 ring-focus">
                      {currentAssignment.lecture.estimatedMinutes} min · Read
                    </a>
                  </li>

                  {currentAssignment.readings.map((reading, index) => {
                    const readingUrl = publicLink(reading.libraryUrl);
                    return (
                      <li key={reading.readingId} className="grid gap-2 border-b border-slate-800/50 py-5 sm:grid-cols-[2rem_minmax(0,1fr)_auto] sm:items-start">
                        <span className="font-sans text-[10px] tracking-[0.2em] text-slate-600">{String(index + 2).padStart(2, '0')}</span>
                        <div>
                          <p className="font-serif text-xl text-slate-100">Read {reading.title}</p>
                          <p className="mt-1 max-w-xl font-serif text-sm leading-relaxed text-slate-500">{reading.recommendedSection}</p>
                        </div>
                        {readingUrl ? (
                          <a href={readingUrl} className="font-sans text-[10px] uppercase tracking-[0.2em] text-amber-200 hover:text-amber-100 ring-focus">
                            {reading.estimatedMinutes ? `${reading.estimatedMinutes} min · ` : ''}Open
                          </a>
                        ) : null}
                      </li>
                    );
                  })}

                  <li className="grid gap-2 border-b border-slate-800/50 py-5 sm:grid-cols-[2rem_minmax(0,1fr)_auto] sm:items-start">
                    <span className="font-sans text-[10px] tracking-[0.2em] text-slate-600">{String(currentAssignment.readings.length + 2).padStart(2, '0')}</span>
                    <div>
                      <p className="font-serif text-xl text-slate-100">Complete the quiz</p>
                      <p className="mt-1 font-serif text-sm text-slate-500">
                        {currentAssignment.quiz.questionCount} questions · passing threshold {currentAssignment.quiz.passingThreshold}%
                      </p>
                    </div>
                    <a href={publicLink(currentAssignment.quiz.url) ?? '#quiz'} className="font-sans text-[10px] uppercase tracking-[0.2em] text-amber-200 hover:text-amber-100 ring-focus">
                      Begin
                    </a>
                  </li>
                </ol>
              </div>
            ) : (
              <p className="font-serif text-lg italic leading-relaxed text-slate-400">
                {assignmentServiceAvailable
                  ? 'No weekly assignment is published yet.'
                  : 'This week’s assignment is temporarily unavailable. Please check back shortly.'}
              </p>
            )}
          </div>
        </section>

        <section className="border-b border-slate-800/60 py-12" aria-labelledby="subjects">
          <div className="grid gap-8 md:grid-cols-[10rem_minmax(0,1fr)]">
            <h2 id="subjects" className="font-sans text-xs font-semibold uppercase tracking-[0.28em] text-slate-300">
              {profile.identity.givenName}&apos;s Subjects
            </h2>
            <ul className="grid border-t border-slate-800/50 sm:grid-cols-2">
              {coachingAreas.map((field, index) => (
                <li key={field} className={`border-b border-slate-800/50 py-5 font-serif text-xl text-slate-200 ${index % 2 === 0 ? 'sm:pr-6' : 'sm:border-l sm:pl-6'}`}>
                  {field}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="border-b border-slate-800/60 py-12" aria-labelledby="about-professor">
          <div className="grid gap-8 md:grid-cols-[10rem_minmax(0,1fr)]">
            <h2 id="about-professor" className="font-sans text-xs font-semibold uppercase tracking-[0.28em] text-slate-300">
              About {profile.identity.givenName}
            </h2>
            <div className="max-w-2xl space-y-4 font-serif leading-relaxed text-slate-300">
              <p>
                {profile.identity.givenName} is a synthetic faculty character, not a human academic.
                Her stable identity and teaching personality come from the School of Chat Character
                Directory; Arc Codex supplies the library and source trail behind the class.
              </p>
              <p>
                Lectures are assembled from identified material and retain their professor, process,
                audience, language, generation date, and sources. The character gives the teaching a
                recognizable voice; the provenance below shows the evidence and editorial process
                rather than asking readers to pretend she is real.
              </p>
            </div>
          </div>
        </section>

        {currentLecture?.lecture_text && (
          <article id="lecture" className="scroll-mt-8 border-b border-slate-800/60 py-12" aria-labelledby="lecture-title">
            <div className="grid gap-8 md:grid-cols-[10rem_minmax(0,1fr)]">
              <div className="space-y-3">
                <p className="font-sans text-xs font-semibold uppercase tracking-[0.28em] text-amber-300/80">Lecture</p>
                <p className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-600">
                  {currentLecture.estimated_minutes} minutes
                </p>
              </div>
              <div className="max-w-3xl">
                <h2 id="lecture-title" className="mb-8 font-serif text-3xl font-semibold leading-tight text-slate-50 sm:text-4xl">
                  {currentLecture.title}
                </h2>
                <div className="space-y-5">
                  {lectureBlocks(currentLecture.lecture_text).map((block, index) =>
                    block.kind === 'heading' ? (
                      <h3 key={`${index}-${block.text}`} className="pt-5 font-sans text-xs font-semibold uppercase tracking-[0.25em] text-slate-300">
                        {block.text}
                      </h3>
                    ) : (
                      <p key={`${index}-${block.text.slice(0, 20)}`} className="font-serif text-[1.05rem] leading-8 text-slate-300">
                        {block.text}
                      </p>
                    ),
                  )}
                </div>
              </div>
            </div>
          </article>
        )}

        {currentLecture?.readings?.length ? (
          <section className="border-b border-slate-800/60 py-12" aria-labelledby="reading">
            <div className="grid gap-8 md:grid-cols-[10rem_minmax(0,1fr)]">
              <h2 id="reading" className="font-sans text-xs font-semibold uppercase tracking-[0.28em] text-slate-300">Reading</h2>
              <ul className="space-y-6">
                {currentLecture.readings.map((reading) => {
                  const readingUrl = publicLink(reading.library_url);
                  return (
                    <li key={reading.reading_id} className="border-l border-slate-700 pl-5">
                      <h3 className="font-serif text-2xl text-slate-100">{reading.title}</h3>
                      <p className="mt-1 font-serif text-slate-400">{reading.author}</p>
                      <p className="mt-3 max-w-2xl font-serif leading-relaxed text-slate-300">{reading.recommended_section}</p>
                      <p className="mt-2 font-sans text-[10px] uppercase tracking-[0.2em] text-slate-600">About {reading.estimated_minutes} minutes</p>
                      {readingUrl && (
                        <a href={readingUrl} className="mt-4 inline-flex items-center gap-2 font-sans text-[10px] uppercase tracking-[0.2em] text-amber-200 transition-colors hover:text-amber-100 ring-focus">
                          <Library className="h-3.5 w-3.5" aria-hidden="true" /> Open in Arc Codex Library
                        </a>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          </section>
        ) : null}

        {currentLecture?.quiz_questions?.length && !currentLecture.assessment_authority ? (
          <section id="quiz" className="scroll-mt-8 border-b border-slate-800/60 py-12" aria-labelledby="quiz-title">
            <div className="grid gap-8 md:grid-cols-[10rem_minmax(0,1fr)]">
              <div className="space-y-3">
                <h2 id="quiz-title" className="font-sans text-xs font-semibold uppercase tracking-[0.28em] text-slate-300">Quiz</h2>
                <p className="font-sans text-[10px] uppercase tracking-[0.2em] text-slate-600">Pass · {currentLecture.passing_threshold}%</p>
              </div>
              <ol className="space-y-8">
                {currentLecture.quiz_questions.map((item) => {
                  const answer = item.choices[item.correct_answer];
                  return (
                    <li key={item.question_id} className="border-t border-slate-800/50 pt-5">
                      <h3 className="font-serif text-lg leading-relaxed text-slate-100">
                        <span className="mr-2 text-slate-600">{item.question_order}.</span>{item.question}
                      </h3>
                      <ol className="mt-4 space-y-2 font-serif text-slate-400" type="A">
                        {item.choices.map((choice) => <li key={choice} className="ml-6 pl-2">{choice}</li>)}
                      </ol>
                      <details className="group mt-4 border-l border-slate-700 pl-4">
                        <summary className="cursor-pointer list-none font-sans text-[10px] uppercase tracking-[0.2em] text-amber-200 ring-focus">
                          Check answer
                        </summary>
                        <div className="mt-3 space-y-2 font-serif leading-relaxed text-slate-300">
                          <p><span className="text-slate-500">Correct:</span> {answer}</p>
                          <p className="text-slate-400">{item.explanation}</p>
                        </div>
                      </details>
                    </li>
                  );
                })}
              </ol>
            </div>
          </section>
        ) : null}

        {currentLecture?.sources?.length ? (
          <section id="sources" className="scroll-mt-8 border-b border-slate-800/60 py-12" aria-labelledby="sources-title">
            <div className="grid gap-8 md:grid-cols-[10rem_minmax(0,1fr)]">
              <h2 id="sources-title" className="font-sans text-xs font-semibold uppercase tracking-[0.28em] text-slate-300">Sources</h2>
              <div className="space-y-8">
                <ol className="space-y-6">
                  {currentLecture.sources.map((source, index) => {
                    const sourceUrl = publicLink(source.url);
                    return (
                      <li key={source.source_id} className="border-t border-slate-800/50 pt-5">
                        <p className="font-sans text-[9px] uppercase tracking-[0.22em] text-slate-600">
                          {String(index + 1).padStart(2, '0')} · {humanize(source.source_type)}{source.public_domain ? ' · Public domain' : ''}
                        </p>
                        <h3 className="mt-2 font-serif text-xl text-slate-100">{source.title}</h3>
                        <p className="mt-1 font-serif text-slate-400">{source.author}</p>
                        <p className="mt-3 font-serif text-sm leading-relaxed text-slate-500">{source.citation}</p>
                        <p className="mt-2 font-serif text-sm italic leading-relaxed text-slate-500">Used: {source.section_used}</p>
                        {sourceUrl && (
                          <a href={sourceUrl} target={sourceUrl.startsWith('https://arc-codex.com/') ? undefined : '_blank'} rel={sourceUrl.startsWith('https://arc-codex.com/') ? undefined : 'noopener noreferrer'} className="mt-3 inline-flex items-center gap-2 font-sans text-[10px] uppercase tracking-[0.2em] text-amber-200 transition-colors hover:text-amber-100 ring-focus">
                            View source <ExternalLink className="h-3 w-3" aria-hidden="true" />
                          </a>
                        )}
                      </li>
                    );
                  })}
                </ol>

                <aside className="border-l border-amber-300/30 pl-5" aria-label="Lecture provenance">
                  <h3 className="font-sans text-[10px] font-semibold uppercase tracking-[0.24em] text-amber-300/80">Provenance</h3>
                  <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
                    <div>
                      <dt className="font-sans text-[9px] uppercase tracking-[0.2em] text-slate-600">Professor</dt>
                      <dd className="mt-1 font-serif text-slate-300">{profile.identity.displayName}</dd>
                    </div>
                    <div>
                      <dt className="font-sans text-[9px] uppercase tracking-[0.2em] text-slate-600">Created</dt>
                      <dd className="mt-1 font-serif text-slate-300">{formatDate(currentLecture.created_at)}</dd>
                    </div>
                    <div>
                      <dt className="font-sans text-[9px] uppercase tracking-[0.2em] text-slate-600">Audience · Language</dt>
                      <dd className="mt-1 font-serif text-slate-300">{humanize(currentLecture.audience)} · {currentLecture.language.toUpperCase()}</dd>
                    </div>
                    <div>
                      <dt className="font-sans text-[9px] uppercase tracking-[0.2em] text-slate-600">Process</dt>
                      <dd className="mt-1 font-serif text-slate-300">{currentLecture.process_name} · v{currentLecture.process_version}</dd>
                    </div>
                  </dl>
                  {currentLecture.provenance?.generation_mode && (
                    <p className="mt-4 font-serif text-sm leading-relaxed text-slate-500">{currentLecture.provenance.generation_mode}</p>
                  )}
                  {currentLecture.provenance?.editorial_note && (
                    <p className="mt-2 font-serif text-sm leading-relaxed text-slate-500">{currentLecture.provenance.editorial_note}</p>
                  )}
                </aside>
              </div>
            </div>
          </section>
        ) : null}

        <section className="py-12" aria-labelledby="latest-lectures">
          <div className="grid gap-8 md:grid-cols-[10rem_minmax(0,1fr)]">
            <h2 id="latest-lectures" className="font-sans text-xs font-semibold uppercase tracking-[0.28em] text-slate-300">Recent Classes</h2>
            {lectures.length ? (
              <ol className="border-t border-slate-800/50">
                {lectures.map((lecture) => (
                  <li key={lecture.lecture_id} className="border-b border-slate-800/50 py-5">
                    <a href={lecture.lecture_id === current?.lecture_id ? '#lecture' : '#now-teaching'} className="group block ring-focus">
                      <p className="font-serif text-xl text-slate-100 transition-colors group-hover:text-amber-100">{lecture.title}</p>
                      <p className="mt-1 font-serif text-sm text-slate-500">{lecture.subject} · {humanize(lecture.audience)} · {lecture.estimated_minutes} minutes</p>
                    </a>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="font-serif italic text-slate-500">No additional lectures yet.</p>
            )}
          </div>
        </section>

        <footer className="border-t border-slate-800/60 py-8 text-center font-sans text-[9px] uppercase tracking-[0.25em] text-slate-600">
          <p>School of Chat · Arc Codex · Synthetic faculty with visible provenance</p>
        </footer>
      </main>
    </div>
  );
}
