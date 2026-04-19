import { requestFormData } from "@/api/client";
import type { UploadResponse } from "@/types";

export async function uploadDocuments(formData: FormData): Promise<UploadResponse> {
  return requestFormData<UploadResponse>("/upload", formData);
}
