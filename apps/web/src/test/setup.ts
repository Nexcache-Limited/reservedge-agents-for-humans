import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { sessionMemoryInternals } from "../session/memory.js";

const originalGetRootNode = Node.prototype.getRootNode;
Node.prototype.getRootNode = function getRootNode(this: Node, options?: GetRootNodeOptions) {
  if (this.ownerDocument?.contains(this)) {
    return this.ownerDocument;
  }
  return originalGetRootNode.call(this, options);
};

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();

  get length(): number {
    return this.values.size;
  }

  clear(): void {
    this.values.clear();
  }

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  key(index: number): string | null {
    return [...this.values.keys()][index] ?? null;
  }

  removeItem(key: string): void {
    this.values.delete(key);
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

Object.defineProperty(globalThis, "sessionStorage", {
  configurable: true,
  value: new MemoryStorage(),
});

afterEach(() => {
  sessionStorage.clear();
  sessionMemoryInternals.a4Keys.clear();
});
