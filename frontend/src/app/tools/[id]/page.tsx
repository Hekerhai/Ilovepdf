import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ToolWorkspace } from "@/components/ToolWorkspace";
import { catalog, getTool } from "@/lib/tools";

type Props = { params: Promise<{ id: string }> };

export function generateStaticParams() {
  return catalog.tools.map((t) => ({ id: t.id }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const tool = getTool((await params).id);
  if (!tool) return {};
  return { title: `${tool.name} online, free`, description: tool.description };
}

export default async function ToolPage({ params }: Props) {
  const tool = getTool((await params).id);
  if (!tool) notFound();
  return <ToolWorkspace tool={tool} />;
}
