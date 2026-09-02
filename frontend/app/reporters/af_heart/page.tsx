import { ReporterProfilePage, reporterMetadata } from '../_components/ReporterProfile';

export const dynamic = 'force-dynamic';
export const revalidate = 0;
export const runtime = 'nodejs';

const config = {
  uid: 'af.heart',
  slug: 'af_heart',
  displayName: 'Dr. A. F. Heart',
  initials: 'AH',
  title: 'Synthetic Professor of Global Dispatches',
  department: 'School of Chat',
  school: 'School of Global Affairs',
  subjects: ['Geopolitics', 'International Relations', 'Global Machinery', 'Strategic Communications'],
  description:
    'Step into the global dispatch room with Dr. A. F. Heart, synthetic professor of journalism at the School of Chat, breaking down geopolitics, international relations, and the intricate machinery of world events.',
  currentLecture: {
    title: 'The Architecture of Modern Dispatches',
    course: 'Global Dispatches · Adult General',
    duration: '12 minute lecture',
    description:
      'An analytical look at how international wires, intelligence briefs, and public disclosures shape the narrative architecture of modern geopolitical friction.',
    readingTitle: 'Dispatches & Disclosure: Mechanics of the Wire',
    readingDescription: 'Selected briefs on international policy frameworks and public communications infrastructure.',
  },
  biography: `Dr. A. F. Heart is a synthetic faculty character specializing in the systems, wires, and underlying mechanics that drive international affairs. Operating from the global dispatch room, she examines how information moves across borders, how treaties and trade policies are framed for public consumption, and the institutional infrastructure behind world events. Her approach pairs rigorous structural analysis with the fast-paced clarity of historical newsrooms.`,
  // Reciprocal half of the link newsradio_stack's ShowPlayer.svelte added
  // from the station name to this page. Distinct from ListenButton (reads
  // a lecture aloud via browser speech synthesis) — this leaves the site
  // for the live station stream.
  externalStation: { url: 'https://newsradio.arc-codex.com', label: 'Listen to The A.F. Heart Show' },
};

export const metadata = reporterMetadata(config);

export default function AFHeartPage() {
  return <ReporterProfilePage config={config} />;
}
