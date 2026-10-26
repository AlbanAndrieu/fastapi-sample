// Rendering the same state must not mutate an observed DOM subtree again.
// The caller performs actual DOM writes only when this function returns true.
export function shouldUpdateRenderSignature(element, signature) {
  if (element.dataset.renderSignature === signature) return false;
  element.dataset.renderSignature = signature;
  return true;
}
