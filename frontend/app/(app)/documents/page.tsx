"use client";

import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Upload, BookOpen, RefreshCw } from "lucide-react";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SkeletonTableRows } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { cn, titleCase } from "@/lib/utils";

interface DocumentOut {
  id: string;
  document_type: string;
  status: string;
  title: string;
  filename: string;
  page_count: number | null;
  current_version: number;
  error_message: string | null;
}

const DOCUMENT_TYPES = [
  "act",
  "rule",
  "notification",
  "circular",
  "faq",
  "case_knowledge",
  "internal_policy",
  "other",
];

const STATUS_VARIANT: Record<string, "good" | "warning" | "critical" | "outline"> = {
  indexed: "good",
  processing: "warning",
  uploaded: "outline",
  failed: "critical",
  archived: "outline",
};

export default function DocumentsPage() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [title, setTitle] = useState("");
  const [documentType, setDocumentType] = useState("faq");
  const [fileName, setFileName] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [reindexing, setReindexing] = useState<string | null>(null);

  const documents = useQuery({
    queryKey: ["documents"],
    queryFn: async () => (await apiClient.get<DocumentOut[]>("/documents")).data,
    retry: false,
    // Ingestion (OCR + embed + index) runs in the background — poll until the
    // row flips from "processing" to "indexed" / "failed".
    refetchInterval: (query) =>
      (query.state.data ?? []).some((d) => ["processing", "uploaded"].includes(d.status))
        ? 3000
        : false,
  });

  function pickFile(f: File | undefined) {
    if (!f) return;
    setFileName(f.name);
    if (!title.trim()) setTitle(f.name.replace(/\.[^.]+$/, ""));
  }

  async function handleUpload(file?: File) {
    const selected = file ?? fileInputRef.current?.files?.[0];
    if (!selected) {
      toast.warning("No file selected", "Choose a document to upload.");
      return;
    }
    const effectiveTitle = title.trim() || selected.name.replace(/\.[^.]+$/, "");

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", selected);
      formData.append("document_type", documentType);
      formData.append("title", effectiveTitle);
      await apiClient.post("/documents/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(
        "Document uploaded",
        `"${effectiveTitle}" is being indexed — the row updates when it's ready.`
      );
      setTitle("");
      setFileName(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      toast.error("Upload failed", getApiErrorMessage(err));
    } finally {
      setUploading(false);
      // Refetch regardless — the row may have been created even if the
      // response was slow or errored client-side.
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ["documents"] }), 2500);
    }
  }

  async function reindex(doc: DocumentOut) {
    setReindexing(doc.id);
    try {
      await apiClient.post(`/documents/${doc.id}/reindex`);
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
      toast.success("Re-indexing started", `"${doc.title}" is being re-processed in the background.`);
    } catch (err) {
      toast.error("Re-index failed", getApiErrorMessage(err));
    } finally {
      setReindexing(null);
    }
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="glass sticky top-0 z-20 flex h-16 shrink-0 items-center border-b border-border px-6">
        <div>
          <h1 className="text-base font-semibold">Knowledge documents</h1>
          <p className="text-xs text-muted-foreground">
            GST Acts, Rules, Notifications, Circulars and FAQs the assistant cites from
          </p>
        </div>
      </header>

      <main className="flex-1 space-y-5 p-6">
        <Card className="p-5">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_auto]">
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex min-w-[220px] flex-1 flex-col gap-1.5">
                <label htmlFor="doc-title" className="text-xs font-medium text-muted-foreground">
                  Title <span className="font-normal">(optional — defaults to the file name)</span>
                </label>
                <Input
                  id="doc-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. CGST Act 2017"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="doc-type" className="text-xs font-medium text-muted-foreground">
                  Type
                </label>
                <Select
                  id="doc-type"
                  value={documentType}
                  onChange={(e) => setDocumentType(e.target.value)}
                >
                  {DOCUMENT_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {titleCase(t)}
                    </option>
                  ))}
                </Select>
              </div>
            </div>
          </div>

          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              const file = e.dataTransfer.files?.[0];
              if (file) {
                pickFile(file);
                handleUpload(file);
              }
            }}
            onClick={() => fileInputRef.current?.click()}
            className={cn(
              "mt-4 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-7 text-center",
              "transition-all duration-300 ease-out",
              dragging
                ? "-translate-y-1 scale-[1.01] border-primary bg-primary-wash shadow-[var(--elev-3),var(--edge-top-strong)]"
                : "border-border bg-elevated/40 shadow-[inset_0_2px_8px_rgba(0,0,0,0.28)] hover:border-border-strong hover:bg-elevated"
            )}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.xlsx,.csv,.txt,.json,.html,.png,.jpg,.jpeg,.tiff"
              className="hidden"
              onChange={(e) => pickFile(e.target.files?.[0] ?? undefined)}
            />
            <Upload
              className={cn(
                "h-5 w-5 transition-transform duration-200",
                dragging ? "scale-110 text-primary" : "text-muted-foreground"
              )}
            />
            <p className="text-sm font-medium">
              {fileName ?? "Drop a document here, or click to browse"}
            </p>
            <p className="text-xs text-muted-foreground">
              PDF, DOCX, XLSX, CSV, TXT, JSON, HTML or scanned image
            </p>
          </div>

          <div className="mt-4 flex justify-end">
            <Button onClick={() => handleUpload()} loading={uploading}>
              {!uploading && <Upload className="h-4 w-4" />}
              {uploading ? "Indexing…" : "Upload & index"}
            </Button>
          </div>
        </Card>

        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-elevated text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">Title</th>
                  <th className="px-4 py-3 font-medium">Type</th>
                  <th className="px-4 py-3 text-right font-medium">Pages</th>
                  <th className="px-4 py-3 text-right font-medium">Version</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {documents.isLoading && <SkeletonTableRows rows={5} cols={6} />}

                {!documents.isLoading &&
                  documents.data?.map((doc) => (
                    <tr
                      key={doc.id}
                      className="group border-b border-border transition-colors last:border-0 hover:bg-elevated"
                    >
                      <td className="px-4 py-3">
                        <div className="font-medium">{doc.title}</div>
                        <div className="text-xs text-muted-foreground">{doc.filename}</div>
                        {doc.error_message && (
                          <div className="mt-0.5 text-xs text-critical">{doc.error_message}</div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-secondary">
                        {titleCase(doc.document_type)}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                        {doc.page_count ?? "—"}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                        v{doc.current_version}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={STATUS_VARIANT[doc.status] ?? "outline"}>
                          {titleCase(doc.status)}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => reindex(doc)}
                          loading={reindexing === doc.id}
                          className="opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                        >
                          {reindexing !== doc.id && <RefreshCw className="h-3.5 w-3.5" />}
                          Re-index
                        </Button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>

          {!documents.isLoading && (documents.data?.length ?? 0) === 0 && (
            <div className="flex flex-col items-center gap-2 py-14">
              <BookOpen className="h-6 w-6 text-muted-foreground" />
              <p className="text-sm font-medium">No documents indexed yet</p>
              <p className="max-w-sm text-center text-xs text-muted-foreground">
                Upload GST Acts, Rules or Circulars above. Until something is indexed, the
                assistant has no sources to ground its answers in.
              </p>
            </div>
          )}
        </Card>
      </main>
    </div>
  );
}
