export function getErrorMessage(error: unknown) {
  if (error && typeof error === 'object' && 'message' in error) {
    return String((error as { message?: unknown }).message || error);
  }
  return error instanceof Error ? error.message : String(error);
}
