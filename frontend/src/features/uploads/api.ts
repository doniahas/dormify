import { api, getErrorMessage } from "../../shared/api/client";
import type { Id } from "../../shared/api/contracts";
import type {
  BatchActionResponse,
  ImportBatch,
  ImportBatchKind,
  InitBatchResponse,
  UploadResponse,
} from "./types";

export const uploadAPI = {
  // Step 1 of the two-step handshake: create the ImportBatch (kind: 'main'
  // or 'additions') and get its id BEFORE any file is sent, so Stop/Status
  // can target an explicit batch_id from the very start of the upload.
  initBatch: async (kind: ImportBatchKind): Promise<InitBatchResponse> => {
    try {
      const { data } = await api.post<InitBatchResponse>("/api/upload/batches/init/", { kind });
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to initialize upload"));
    }
  },

  getBatchStatus: async (batchId: Id): Promise<ImportBatch> => {
    try {
      const { data } = await api.get<ImportBatch>(`/api/upload/batches/${batchId}/status/`);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to fetch upload status"));
    }
  },

  stopBatch: async (batchId: Id): Promise<BatchActionResponse> => {
    try {
      const { data } = await api.post<BatchActionResponse>(`/api/upload/batches/${batchId}/stop/`);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to stop upload"));
    }
  },

  stopAndDeleteBatch: async (batchId: Id): Promise<BatchActionResponse> => {
    try {
      const { data } = await api.post<BatchActionResponse>(`/api/upload/batches/${batchId}/stop-and-delete/`);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to stop and delete upload"));
    }
  },

  deleteBatch: async (batchId: Id): Promise<BatchActionResponse> => {
    try {
      const { data } = await api.post<BatchActionResponse>(`/api/upload/batches/${batchId}/delete/`);
      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Failed to delete uploaded students"));
    }
  },

  // Step 2 of the handshake: batchId must come from initBatch() above.
  uploadExcel: async (file: Blob, batchId: Id): Promise<UploadResponse> => {
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("batch_id", String(batchId));

      const { data } = await api.post<UploadResponse>("/api/upload/excel/", form, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });

      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Excel upload failed"));
    }
  },

  uploadAdditionsExcel: async (file: Blob, batchId: Id): Promise<UploadResponse> => {
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("batch_id", String(batchId));

      const { data } = await api.post<UploadResponse>("/api/upload/additions-excel/", form, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });

      return data;
    } catch (err) {
      throw new Error(getErrorMessage(err, "Additions Excel upload failed"));
    }
  },
};
