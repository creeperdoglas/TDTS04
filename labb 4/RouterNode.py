#!/usr/bin/env python
#code by melgu374 and antfo614
import GuiTextArea, RouterPacket, F
from copy import deepcopy

class RouterNode():
    def __init__(self, ID, sim, costs):
        self.myID = ID
        self.sim = sim
        self.myGUI = GuiTextArea.GuiTextArea(f"Output window for Router #{ID}")

        self.costs = deepcopy(costs)
        self.neighbors = [i for i in range(len(costs)) if costs[i] != sim.INFINITY and i != ID]
        self.distanceTable = [[sim.INFINITY]*sim.NUM_NODES for _ in range(sim.NUM_NODES)]
        self.distanceVectors = [[sim.INFINITY for _ in range(sim.NUM_NODES)] for _ in range(sim.NUM_NODES)]
        self.distanceVector = deepcopy(costs)
        self.nextHops = [i if costs[i] != sim.INFINITY else None for i in range(sim.NUM_NODES)]

        self.initRouteTable()
        self.propagate()

    def initRouteTable(self):
        for i in range(self.sim.NUM_NODES):
            if self.costs[i] != self.sim.INFINITY and i != self.myID:
                self.distanceTable[self.myID][i] = self.costs[i]
                self.nextHops[i] = i
            else:
                self.distanceTable[self.myID][i] = self.sim.INFINITY
                self.nextHops[i] = None

    def recvUpdate(self, pkt):
        source = pkt.sourceid
        self.distanceVectors[source] = pkt.mincost
        updated = False

        for dest in range(self.sim.NUM_NODES):
            if dest == self.myID:
                continue
            min_cost = self.costs[dest]
            next_hop = self.nextHops[dest]

            for neighbor in self.neighbors:
                if self.costs[neighbor] + self.distanceVectors[neighbor][dest] < min_cost:
                    min_cost = self.costs[neighbor] + self.distanceVectors[neighbor][dest]
                    next_hop = neighbor

            if min_cost != self.distanceVector[dest]:
                self.distanceVector[dest] = min_cost
                self.nextHops[dest] = next_hop
                updated = True

        if updated:
            self.propagate()

    def propagate(self):
        for neighbor in self.neighbors:
            sendVector = deepcopy(self.distanceVector)

            if self.sim.POISONREVERSE:
                for i in range(self.sim.NUM_NODES):
                    if self.nextHops[i] == neighbor:
                        sendVector[i] = self.sim.INFINITY

            packet = RouterPacket.RouterPacket(self.myID, neighbor, sendVector)
            self.sim.toLayer2(packet)

    def updateLinkCost(self, dest, newcost):
        self.costs[dest] = newcost = newcost
        self.distanceVector[dest] = newcost
        self.distanceTable[self.myID][dest] = newcost

        updated = False

        for dest in range(self.sim.NUM_NODES):
            min_cost = min(self.costs[neighbor] + self.distanceVectors[neighbor][dest] for neighbor in self.neighbors)
            if min_cost != self.distanceVector[dest]:
                self.distanceVector[dest] = min_cost
                updated = True

        if updated:
            self.propagate()

    def printDistanceTable(self):
        self.myGUI.println(f"Distance table for router #{self.myID} at time {self.sim.getClocktime()}")
        self.myGUI.println("Dest | Cost | Next hop")
        self.myGUI.println("------------------------")
        for dest in range(self.sim.NUM_NODES):
            if dest != self.myID:
                next_hop = self.nextHops[dest] if self.nextHops[dest] is not None else '-'
                self.myGUI.println(f"{dest}    | {self.distanceVector[dest]}    | {next_hop}")
