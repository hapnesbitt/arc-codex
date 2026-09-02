import { ReporterProfilePage, reporterMetadata } from '../_components/ReporterProfile';

export const dynamic = 'force-dynamic';
export const revalidate = 0;
export const runtime = 'nodejs';

const config = {
  uid: 'torchy.blane',
  slug: 'torchy_blane',
  displayName: 'Dr. Torchy Blane',
  initials: 'TB',
  description:
    'Step into the deadline-driven seminar room with Dr. Torchy Blane, synthetic professor of comparative literature, exploring the immortal cadence of The Odyssey.',
};

export const metadata = reporterMetadata(config);

export default function TorchyBlanePage() {
  return <ReporterProfilePage config={config} />;
}
