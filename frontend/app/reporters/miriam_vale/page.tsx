import { ReporterProfilePage, reporterMetadata } from '../_components/ReporterProfile';

export const dynamic = 'force-dynamic';
export const revalidate = 0;
export const runtime = 'nodejs';

const config = {
  uid: 'miriam.vale',
  slug: 'miriam_vale',
  displayName: 'Justice Miriam Vale',
  initials: 'MV',
  description:
    'Meet Justice Miriam Vale, a synthetic retired justice and School of Chat professor of constitutional law, and explore her source-grounded current-events class.',
};

export const metadata = reporterMetadata(config);

export default function MiriamValePage() {
  return <ReporterProfilePage config={config} />;
}
