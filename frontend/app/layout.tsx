import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AutoOpsHub - 自动化运维平台",
  description: "企业级自动化运维管理平台，支持 Terraform、Ansible、Script 和 Workflow 类型的运行手册管理",
};

export const viewport: Viewport = {
  themeColor: "#1a1a2e",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" className="bg-background">
      <body className="min-h-screen font-sans antialiased">
        {children}
      </body>
    </html>
  );
}
