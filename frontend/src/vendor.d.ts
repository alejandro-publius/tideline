// world-atlas ships pre-built TopoJSON as raw .json; give the import a type so
// topojson-client's `mesh()` accepts it without an `any` cast.
declare module 'world-atlas/land-110m.json' {
  import type { Topology, GeometryCollection } from 'topojson-specification'
  const topology: Topology<{ land: GeometryCollection }>
  export default topology
}
