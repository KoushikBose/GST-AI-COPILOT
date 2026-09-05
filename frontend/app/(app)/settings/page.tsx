"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Save, User, Building2, BadgeCheck } from "lucide-react";
import { apiClient, getApiErrorMessage } from "@/lib/api-client";
import { useAuthStore } from "@/lib/auth-store";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { toast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

interface Organization {
  id: string;
  name: string;
  legal_name: string | null;
  slug: string;
  gst_profile: {
    gstin: string;
    legal_name: string;
    trade_name: string | null;
    state_code: string;
    registration_type: string;
    is_verified: boolean;
  } | null;
}

const REGISTRATION_TYPES = ["regular", "composition", "casual", "sez", "input_service_distributor"];

function Field({
  label,
  ...props
}: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <Input {...props} />
    </label>
  );
}

function ProfileTab() {
  const setUser = useAuthStore((s) => s.setUser);
  const user = useAuthStore((s) => s.user);
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => setFullName(user?.full_name ?? ""), [user?.full_name]);

  async function save() {
    setSaving(true);
    try {
      const body: Record<string, string> = {};
      if (fullName && fullName !== user?.full_name) body.full_name = fullName;
      if (newPassword) {
        body.current_password = currentPassword;
        body.new_password = newPassword;
      }
      const { data } = await apiClient.patch("/auth/me", body);
      setUser(data);
      setCurrentPassword("");
      setNewPassword("");
      toast.success("Profile updated");
    } catch (err) {
      toast.error("Update failed", getApiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Your profile</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <Field label="Email" value={user?.email ?? ""} disabled />
        <Field
          label="Full name"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field
            label="Current password"
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            placeholder="Only to change password"
          />
          <Field
            label="New password"
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="At least 10 characters"
          />
        </div>
        <div className="flex justify-end">
          <Button onClick={save} loading={saving}>
            {!saving && <Save className="h-4 w-4" />}
            Save profile
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function OrganizationTab() {
  const queryClient = useQueryClient();
  const org = useQuery({
    queryKey: ["organization"],
    queryFn: async () => (await apiClient.get<Organization>("/organizations/current")).data,
    retry: false,
  });

  const [name, setName] = useState("");
  const [legalName, setLegalName] = useState("");
  const [gstin, setGstin] = useState("");
  const [tradeName, setTradeName] = useState("");
  const [stateCode, setStateCode] = useState("");
  const [regType, setRegType] = useState("regular");
  const [savingOrg, setSavingOrg] = useState(false);
  const [savingGst, setSavingGst] = useState(false);

  useEffect(() => {
    if (!org.data) return;
    setName(org.data.name);
    setLegalName(org.data.legal_name ?? "");
    setGstin(org.data.gst_profile?.gstin ?? "");
    setTradeName(org.data.gst_profile?.trade_name ?? "");
    setStateCode(org.data.gst_profile?.state_code ?? "");
    setRegType(org.data.gst_profile?.registration_type ?? "regular");
  }, [org.data]);

  async function saveOrg() {
    setSavingOrg(true);
    try {
      await apiClient.patch("/organizations/current", { name, legal_name: legalName });
      await queryClient.invalidateQueries({ queryKey: ["organization"] });
      toast.success("Organization updated");
    } catch (err) {
      toast.error("Update failed", getApiErrorMessage(err));
    } finally {
      setSavingOrg(false);
    }
  }

  async function saveGst() {
    setSavingGst(true);
    try {
      await apiClient.put("/organizations/current/gst-profile", {
        gstin,
        legal_name: legalName || name,
        trade_name: tradeName || null,
        state_code: stateCode,
        registration_type: regType,
      });
      await queryClient.invalidateQueries({ queryKey: ["organization"] });
      toast.success("GST profile saved");
    } catch (err) {
      toast.error("Save failed", getApiErrorMessage(err));
    } finally {
      setSavingGst(false);
    }
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Organization</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field label="Display name" value={name} onChange={(e) => setName(e.target.value)} />
          <Field
            label="Legal name"
            value={legalName}
            onChange={(e) => setLegalName(e.target.value)}
          />
          <Field label="Slug" value={org.data?.slug ?? ""} disabled />
          <div className="flex justify-end">
            <Button onClick={saveOrg} loading={savingOrg}>
              {!savingOrg && <Save className="h-4 w-4" />}
              Save
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>GST registration</CardTitle>
          {org.data?.gst_profile && (
            <Badge variant={org.data.gst_profile.is_verified ? "good" : "outline"}>
              <BadgeCheck className="h-3 w-3" />
              {org.data.gst_profile.is_verified ? "Verified" : "Unverified"}
            </Badge>
          )}
        </CardHeader>
        <CardContent className="space-y-4">
          <Field
            label="GSTIN"
            value={gstin}
            onChange={(e) => setGstin(e.target.value.toUpperCase())}
            maxLength={15}
            className="font-mono"
          />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field
              label="Trade name"
              value={tradeName}
              onChange={(e) => setTradeName(e.target.value)}
            />
            <Field
              label="State code"
              value={stateCode}
              onChange={(e) => setStateCode(e.target.value)}
              maxLength={2}
            />
          </div>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="text-xs font-medium text-muted-foreground">Registration type</span>
            <Select value={regType} onChange={(e) => setRegType(e.target.value)}>
              {REGISTRATION_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
          </label>
          <div className="flex justify-end">
            <Button onClick={saveGst} loading={savingGst}>
              {!savingGst && <Save className="h-4 w-4" />}
              Save GST profile
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

const TABS = [
  { id: "profile", label: "Profile", icon: User },
  { id: "organization", label: "Organization", icon: Building2 },
] as const;

export default function SettingsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("profile");

  return (
    <div className="flex flex-1 flex-col">
      <header className="glass sticky top-0 z-20 flex h-16 shrink-0 items-center border-b border-border px-6">
        <div>
          <h1 className="text-base font-semibold">Settings</h1>
          <p className="text-xs text-muted-foreground">Your profile and organization configuration</p>
        </div>
      </header>

      <main className="flex-1 space-y-5 p-6">
        <div className="flex gap-1 rounded-md border border-border p-1">
          {TABS.map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={cn(
                  "flex items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                  tab === t.id
                    ? "bg-primary-wash text-primary"
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {t.label}
              </button>
            );
          })}
        </div>

        <div className="max-w-2xl">
          {tab === "profile" ? <ProfileTab /> : <OrganizationTab />}
        </div>
      </main>
    </div>
  );
}
