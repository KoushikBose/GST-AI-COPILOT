"use client";

import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { UserPlus, ShieldCheck, ScrollText } from "lucide-react";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton, SkeletonTableRows } from "@/components/ui/skeleton";
import { toast } from "@/components/ui/toast";
import { titleCase } from "@/lib/utils";

interface Member {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
}

interface AuditLog {
  id: string;
  actor_user_id: string | null;
  actor_type: string;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  created_at: string;
}

const ROLES = [
  "org_admin",
  "accountant",
  "finance_manager",
  "analyst",
  "reviewer",
  "auditor",
  "viewer",
];

export default function AdminPage() {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("viewer");
  const [adding, setAdding] = useState(false);

  const members = useQuery({
    queryKey: ["members"],
    queryFn: async () => (await apiClient.get<Member[]>("/organizations/current/members")).data,
    retry: false,
  });

  const audit = useQuery({
    queryKey: ["audit"],
    queryFn: async () =>
      (await apiClient.get<AuditLog[]>("/organizations/current/audit", { params: { limit: 50 } }))
        .data,
    retry: false,
  });

  const rows = useMemo(() => members.data ?? [], [members.data]);

  async function addMember() {
    if (!email.trim()) {
      toast.warning("Email required");
      return;
    }
    setAdding(true);
    try {
      await apiClient.post("/organizations/current/members", {
        email,
        role,
        full_name: fullName || null,
        password: password || null,
      });
      await queryClient.invalidateQueries({ queryKey: ["members"] });
      await queryClient.invalidateQueries({ queryKey: ["audit"] });
      toast.success("Member added", `${email} joined as ${titleCase(role)}.`);
      setEmail("");
      setFullName("");
      setPassword("");
    } catch (err) {
      toast.error("Couldn't add member", getApiErrorMessage(err));
    } finally {
      setAdding(false);
    }
  }

  async function patchMember(member: Member, body: { role?: string; is_active?: boolean }) {
    try {
      await apiClient.patch(`/organizations/current/members/${member.id}`, body);
      await queryClient.invalidateQueries({ queryKey: ["members"] });
      await queryClient.invalidateQueries({ queryKey: ["audit"] });
      toast.success("Member updated");
    } catch (err) {
      toast.error("Update failed", getApiErrorMessage(err));
    }
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="glass sticky top-0 z-20 flex h-16 shrink-0 items-center border-b border-border px-6">
        <div>
          <h1 className="text-base font-semibold">Admin console</h1>
          <p className="text-xs text-muted-foreground">
            Members, roles and the organization audit trail
          </p>
        </div>
      </header>

      <main className="flex-1 space-y-5 p-6">
        <Card>
          <CardHeader className="flex-row items-center gap-2">
            <UserPlus className="h-4 w-4 text-primary" />
            <CardTitle>Add a member</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Input
                placeholder="Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <Input
                placeholder="Full name (new users)"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
              <Input
                placeholder="Temp password (new users)"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <Select value={role} onChange={(e) => setRole(e.target.value)}>
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {titleCase(r)}
                  </option>
                ))}
              </Select>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Existing users are added by email only. New users need a name and a temporary
              password.
            </p>
            <div className="mt-3 flex justify-end">
              <Button onClick={addMember} loading={adding}>
                {!adding && <UserPlus className="h-4 w-4" />}
                Add member
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader className="flex-row items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" />
            <CardTitle>Members</CardTitle>
          </CardHeader>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-elevated text-left text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Email</th>
                  <th className="px-4 py-3 font-medium">Role</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {members.isLoading && <SkeletonTableRows rows={4} cols={4} />}
                {rows.map((m) => (
                  <tr key={m.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3 font-medium">{m.full_name}</td>
                    <td className="px-4 py-3 text-muted-foreground">{m.email}</td>
                    <td className="px-4 py-3">
                      <Select
                        value={m.role}
                        onChange={(e) => patchMember(m, { role: e.target.value })}
                        className="h-8 text-xs"
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {titleCase(r)}
                          </option>
                        ))}
                      </Select>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => patchMember(m, { is_active: !m.is_active })}
                        title="Toggle active"
                      >
                        <Badge variant={m.is_active ? "good" : "outline"}>
                          {m.is_active ? "Active" : "Inactive"}
                        </Badge>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card>
          <CardHeader className="flex-row items-center gap-2">
            <ScrollText className="h-4 w-4 text-primary" />
            <CardTitle>Recent activity</CardTitle>
          </CardHeader>
          <CardContent>
            {audit.isLoading && <Skeleton className="h-40 w-full" />}
            {!audit.isLoading && (audit.data?.length ?? 0) === 0 && (
              <p className="text-sm text-muted-foreground">No audit entries yet.</p>
            )}
            <ul className="divide-y divide-border text-sm">
              {(audit.data ?? []).map((log) => (
                <li key={log.id} className="flex items-center justify-between gap-4 py-2">
                  <div className="min-w-0">
                    <span className="font-mono text-xs text-primary">{log.action}</span>
                    {log.entity_type && (
                      <span className="ml-2 text-xs text-muted-foreground">
                        {log.entity_type}
                        {log.entity_id ? ` · ${log.entity_id.slice(0, 8)}…` : ""}
                      </span>
                    )}
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {new Date(log.created_at).toLocaleString("en-IN")}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
