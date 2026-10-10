"""Spatial weights for hexagon zones built from exact edge adjacency."""

from __future__ import annotations

import numpy as np
from libpysal.graph import Graph
from libpysal.weights import W
from numpy.typing import NDArray
from scipy.sparse.csgraph import connected_components

from sgheat.geo.hexgrid import adjacency


def hex_graph(q: NDArray[np.int64], r: NDArray[np.int64]) -> Graph:
    """Row-standardised contiguity graph of hexagons (neighbours share an edge).

    Zones are identified by their row position. Isolated zones are kept with a
    zero-weight self loop, which is how :class:`libpysal.graph.Graph` represents them.
    """
    focal, neighbour = adjacency(q, r)
    n = len(q)
    isolates = np.setdiff1d(np.arange(n), focal)
    focal_all = np.concatenate([focal, isolates])
    neighbour_all = np.concatenate([neighbour, isolates])
    weight = np.concatenate([np.ones(len(focal)), np.zeros(len(isolates))])
    order = np.lexsort((neighbour_all, focal_all))
    graph = Graph.from_arrays(focal_all[order], neighbour_all[order], weight[order])
    return graph.transform("r")


def component_labels(q: NDArray[np.int64], r: NDArray[np.int64]) -> NDArray[np.int64]:
    """Connected component of each zone under edge adjacency."""
    import scipy.sparse as sp  # noqa: PLC0415

    focal, neighbour = adjacency(q, r)
    n = len(q)
    adj = sp.coo_array((np.ones(len(focal)), (focal, neighbour)), shape=(n, n)).tocsr()
    _, labels = connected_components(adj, directed=False)
    return np.asarray(labels, dtype=np.int64)


def largest_component(q: NDArray[np.int64], r: NDArray[np.int64]) -> NDArray[np.bool_]:
    """Mask of the zones in the largest connected component."""
    labels = component_labels(q, r)
    counts = np.bincount(labels)
    return np.asarray(labels == int(np.argmax(counts)), dtype=bool)


def to_w(graph: Graph) -> W:
    """Legacy :class:`libpysal.weights.W` as expected by spreg and esda."""
    w = graph.to_W()
    w.transform = "r"
    return w
