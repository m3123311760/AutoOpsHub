import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { JobsContent } from "@/components/jobs-content";

interface JobsPageProps {
  params: Promise<{
    workpiece: string;
  }>;
}

export default async function JobsPage({ params }: JobsPageProps) {
  const { workpiece } = await params;
  const decodedName = decodeURIComponent(workpiece);

  return (
    <div className="min-h-screen">
      <Sidebar currentWorkpiece={decodedName} />
      <main className="pl-64">
        <Header title="定时作业" description={`${decodedName} 的定时作业管理`} />
        <div className="p-6">
          <JobsContent workpiece={decodedName} />
        </div>
      </main>
    </div>
  );
}
