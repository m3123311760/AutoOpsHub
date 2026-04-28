import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { WorkpieceDetailContent } from "@/components/workpiece-detail-content";

interface WorkpiecePageProps {
  params: Promise<{
    workpiece: string;
  }>;
}

export default async function WorkpieceDetailPage({ params }: WorkpiecePageProps) {
  const { workpiece } = await params;
  const decodedName = decodeURIComponent(workpiece);

  return (
    <div className="min-h-screen">
      <Sidebar currentWorkpiece={decodedName} />
      <main className="pl-64">
        <Header title={decodedName} description="工作区详情" />
        <div className="p-6">
          <WorkpieceDetailContent workpiece={decodedName} />
        </div>
      </main>
    </div>
  );
}
