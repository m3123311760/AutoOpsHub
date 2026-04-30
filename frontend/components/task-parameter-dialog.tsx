"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { ManifestVariable } from "@/lib/api";
import {
  buildInitialManifestValues,
  collectManifestInputVariables,
  parseJsonVariableText,
  type ManifestValueMap,
} from "@/lib/manifest-form";

interface TaskParameterDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  manifestItems: ManifestVariable[];
  initialValues?: Record<string, unknown>;
  fallbackJson?: string;
  submitLabel: string;
  isSubmitting?: boolean;
  errorText?: string;
  onSubmit: (variables: Record<string, unknown>) => void | Promise<void>;
}

function valuesFromManifest(manifestItems: ManifestVariable[], initialValues?: Record<string, unknown>): ManifestValueMap {
  const defaults = buildInitialManifestValues(manifestItems);
  for (const item of manifestItems) {
    const value = initialValues?.[item.name];
    if (value !== undefined && value !== null) {
      defaults[item.name] = String(value);
    }
  }
  return defaults;
}

export function TaskParameterDialog({
  open,
  onOpenChange,
  title,
  description,
  manifestItems,
  initialValues,
  fallbackJson = "{}",
  submitLabel,
  isSubmitting = false,
  errorText,
  onSubmit,
}: TaskParameterDialogProps) {
  const [values, setValues] = useState<ManifestValueMap>({});
  const [jsonText, setJsonText] = useState(fallbackJson);
  const [jsonError, setJsonError] = useState("");

  useEffect(() => {
    if (!open) return;
    setValues(valuesFromManifest(manifestItems, initialValues));
    setJsonText(initialValues ? JSON.stringify(initialValues, null, 2) : fallbackJson);
    setJsonError("");
  }, [fallbackJson, initialValues, manifestItems, open]);

  const inputItems = manifestItems.filter((item) => item.direction === "input");

  const handleSubmit = async () => {
    let variables: Record<string, unknown>;
    if (manifestItems.length > 0) {
      variables = collectManifestInputVariables(manifestItems, values);
    } else {
      try {
        variables = parseJsonVariableText(jsonText);
      } catch (error) {
        setJsonError(error instanceof Error ? error.message : "变量必须是有效 JSON");
        return;
      }
    }
    setJsonError("");
    await onSubmit(variables);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          {manifestItems.length > 0 ? (
            inputItems.map((item) => (
              <div key={item.name} className="grid gap-2">
                <Label htmlFor={`param-${item.name}`}>
                  {item.display_name || item.name}
                  {item.required && <span className="text-destructive"> *</span>}
                </Label>
                <Input
                  id={`param-${item.name}`}
                  value={values[item.name] || ""}
                  onChange={(e) => setValues((current) => ({ ...current, [item.name]: e.target.value }))}
                  placeholder={item.default_value || item.name}
                  required={item.required}
                />
              </div>
            ))
          ) : (
            <div className="grid gap-2">
              <Label htmlFor="param-json">变量 (JSON)</Label>
              <Textarea
                id="param-json"
                className="h-32 font-mono text-sm"
                value={jsonText}
                onChange={(e) => setJsonText(e.target.value)}
                placeholder='{"key": "value"}'
              />
            </div>
          )}
          {(errorText || jsonError) && (
            <div className="rounded-md bg-destructive/10 p-3 text-sm text-destructive">{errorText || jsonError}</div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={isSubmitting}>
            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {submitLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
