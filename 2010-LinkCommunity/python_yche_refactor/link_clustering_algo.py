#!/usr/bin/env python
# encoding: utf-8

from copy import copy
from heapq import heappush, heappop
from itertools import combinations, chain


def get_sorted_pair(a, b):
    if a > b:
        return b, a
    else:
        return a, b


def cal_density(edge_num, vertex_num):
    if vertex_num > 2:
        return edge_num * (edge_num - vertex_num + 1.0) / ((vertex_num - 2.0) * (vertex_num - 1.0))
    else:
        return 0.0


def cal_jaccard(left_set, right_set):
    return 1.0 * len(left_set & right_set) / len(left_set | right_set)


def similarities_unweighted(adj_list_dict):
    i_adj = dict((n, adj_list_dict[n] | {n}) for n in adj_list_dict)
    min_heap = []
    for n in adj_list_dict:
        if len(adj_list_dict[n]) > 1:
            for i, j in combinations(adj_list_dict[n], 2):  # all unordered pairs of neighbors
                edge_pair = get_sorted_pair(get_sorted_pair(i, n), get_sorted_pair(j, n))
                inc_ns_i, inc_ns_j = i_adj[i], i_adj[j]
                S = cal_jaccard(inc_ns_i, inc_ns_j)
                heappush(min_heap, (1 - S, edge_pair))
    return [heappop(min_heap) for i in xrange(len(min_heap))]  # return ordered edge pairs


def similarities_weighted(adj_dict, edge_weight_dict):
    i_adj = dict((n, adj_dict[n] | {n}) for n in adj_dict)
    Aij = copy(edge_weight_dict)
    n2a_sqrd = {}
    for n in adj_dict:
        Aij[n, n] = 1.0 * sum(edge_weight_dict[get_sorted_pair(n, i)] for i in adj_dict[n]) / len(adj_dict[n])
        n2a_sqrd[n] = sum(Aij[get_sorted_pair(n, i)] ** 2 for i in i_adj[n])  # includes (n,n)!

    min_heap = []
    for ind, n in enumerate(adj_dict):
        if len(adj_dict[n]) > 1:
            for i, j in combinations(adj_dict[n], 2):
                edge_pair = get_sorted_pair(get_sorted_pair(i, n), get_sorted_pair(j, n))
                inc_ns_i, inc_ns_j = i_adj[i], i_adj[j]

                ai_dot_aj = 1.0 * sum(
                    Aij[get_sorted_pair(i, x)] * Aij[get_sorted_pair(j, x)] for x in inc_ns_i & inc_ns_j)

                S = ai_dot_aj / (n2a_sqrd[i] + n2a_sqrd[j] - ai_dot_aj)  # tanimoto similarity
                heappush(min_heap, (1 - S, edge_pair))
    return [heappop(min_heap) for i in xrange(len(min_heap))]  # return ordered edge pairs


# Hierarchical Link Community
class HLC:
    def __init__(self, adj_list_dict, edges):
        self.adj = adj_list_dict  # node -> set of neighbors
        self.edges = edges  # list of edges
        self.density_factor = 2.0 / len(edges)

        self.edge2cid = {}
        self.cid2nodes, self.cid2edges = {}, {}
        self.orig_cid2edge = {}
        self.curr_maxcid = 0
        self.linkage = []  # dendrogram

        self.initialize_edges()  # every edge in its own comm
        self.D = 0.0  # partition density

    def initialize_edges(self):
        for cid, edge in enumerate(self.edges):
            edge = get_sorted_pair(*edge)  # just in case
            self.edge2cid[edge] = cid
            self.cid2edges[cid] = {edge}
            self.orig_cid2edge[cid] = edge
            self.cid2nodes[cid] = set(edge)
        self.curr_maxcid = len(self.edges) - 1

    def merge_comms(self, edge1, edge2, S, dendro_flag=False):
        if not edge1 or not edge2:  # We'll get (None, None) at the end of clustering
            return
        cid1, cid2 = self.edge2cid[edge1], self.edge2cid[edge2]
        if cid1 == cid2:  # already merged!
            return
        m1, m2 = len(self.cid2edges[cid1]), len(self.cid2edges[cid2])
        n1, n2 = len(self.cid2nodes[cid1]), len(self.cid2nodes[cid2])
        Dc1, Dc2 = cal_density(m1, n1), cal_density(m2, n2)
        if m2 > m1:  # merge smaller into larger
            cid1, cid2 = cid2, cid1

        if dendro_flag:
            self.curr_maxcid += 1
            newcid = self.curr_maxcid
            self.cid2edges[newcid] = self.cid2edges[cid1] | self.cid2edges[cid2]
            self.cid2nodes[newcid] = set()
            for e in chain(self.cid2edges[cid1], self.cid2edges[cid2]):
                self.cid2nodes[newcid] |= set(e)
                self.edge2cid[e] = newcid
            del self.cid2edges[cid1], self.cid2nodes[cid1]
            del self.cid2edges[cid2], self.cid2nodes[cid2]
            m, n = len(self.cid2edges[newcid]), len(self.cid2nodes[newcid])

            self.linkage.append((cid1, cid2, S))

        else:
            self.cid2edges[cid1] |= self.cid2edges[cid2]
            for e in self.cid2edges[cid2]:  # move edges,nodes from cid2 to cid1
                self.cid2nodes[cid1] |= set(e)
                self.edge2cid[e] = cid1
            del self.cid2edges[cid2], self.cid2nodes[cid2]

            m, n = len(self.cid2edges[cid1]), len(self.cid2nodes[cid1])

        Dc12 = cal_density(m, n)
        self.D += (Dc12 - Dc1 - Dc2) * self.density_factor  # update partition density

    def single_linkage(self, threshold=None, w=None, dendro_flag=False):
        print "clustering..."
        list_D = [(1.0, 0.0)]  # list of (S_i,D_i) tuples...
        best_D = 0.0
        best_S = 1.0  # similarity threshold at best_D
        best_P = None  # best partition, dict: edge -> cid

        if w is None:  # unweighted
            H = similarities_unweighted(self.adj)  # min-heap ordered by 1-s
        else:
            H = similarities_weighted(self.adj, w)
        S_prev = -1

        # (1.0, (None, None)) takes care of the special case where the last
        # merging gives the maximum partition density (e.g. a single clique).
        for oms, eij_eik in chain(H, [(1.0, (None, None))]):
            S = 1 - oms  # remember, H is a min-heap
            if threshold and S < threshold:
                break

            if S != S_prev:  # update list
                if self.D >= best_D:  # check PREVIOUS merger, because that's
                    best_D = self.D  # the end of the tie
                    best_S = S
                    best_P = copy(self.edge2cid)  # slow...
                list_D.append((S, self.D))
                S_prev = S

            self.merge_comms(eij_eik[0], eij_eik[1], S, dendro_flag)

        # list_D.append( (0.0,list_D[-1][1]) ) # add final val
        if threshold is not None:
            return self.edge2cid, self.D
        if dendro_flag:
            return best_P, best_S, best_D, list_D, self.orig_cid2edge, self.linkage
        else:
            return best_P, best_S, best_D, list_D
