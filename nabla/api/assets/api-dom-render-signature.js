// Rendering the same state must not mutate an observed DOM subtree again.
// The caller performs actual DOM writes only when this function returns true.
export function shouldUpdateRenderSignature(element, signature) {
  if (element.dataset.renderSignature === signature) return false;
  element.dataset.renderSignature = signature;
  return true;
}

// MutationObserver attributes can self-trigger on *identical* DOM writes.
// Return false without updating the DOM when the published status is stable.
export function setDatasetValueIfChanged(element, name, value) {
  if (element.dataset[name] === value) return false;
  element.dataset[name] = value;
  return true;
}
