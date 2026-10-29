/** Carries result files from one tool page to the next ("Continue with…") without re-uploading. */
let pending: File[] = [];

export function handOff(files: File[]): void {
  pending = files;
}

export function takeHandOff(): File[] {
  const files = pending;
  pending = [];
  return files;
}
