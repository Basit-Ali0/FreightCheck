import "@testing-library/jest-dom/vitest";

/** jsdom does not implement `scrollIntoView` as a function on all elements. */
Element.prototype.scrollIntoView = function scrollIntoViewPolyfill(): void {
  /* no-op for tests */
};
