#!/usr/bin/env python
# code by melgu374 and antfo614
import GuiTextArea, RouterPacket, F
from copy import deepcopy
from F import F

class RouterNode():
    def __init__(self, ID, sim, costs):
        self.myID = ID
        self.sim = sim
        self.myGUI = GuiTextArea.GuiTextArea(f"Output window for Router #{ID}")

        self.costs = deepcopy(costs)
        self.neighbors = [i for i in range(len(costs)) if costs[i] != sim.INFINITY and costs[i] != 0]
        self.distanceTable = [[sim.INFINITY]*sim.NUM_NODES for _ in range(sim.NUM_NODES)]
        self.distanceVector = deepcopy(costs)
        self.nextHops = [None if costs[i] == sim.INFINITY else i for i in range(sim.NUM_NODES)]

        self.initRouteTable()
        self.propagate()

    def initRouteTable(self):
        for i in range(self.sim.NUM_NODES):
            self.distanceTable[self.myID][i] = self.costs[i]
            if self.costs[i] != self.sim.INFINITY and i != self.myID:
                self.nextHops[i] = i
            else:
                self.nextHops[i] = None

    def recvUpdate(self, pkt):
        source = pkt.sourceid
        updated = False

    
        for dest in range(self.sim.NUM_NODES):
            self.distanceTable[source][dest] = pkt.mincost[dest]

        
        updated = self.calcMincost()

        if updated:
            self.propagate()

    def calcMincost(self):
        updated = False

        for dst in range(self.sim.NUM_NODES):
            if dst == self.myID:
                continue

            min_cost = self.costs[dst]
            next_hop = None if min_cost == self.sim.INFINITY else dst

            for neighbor in self.neighbors:
                potential_cost = self.costs[neighbor] + self.distanceTable[neighbor][dst]
                if potential_cost < min_cost:
                    min_cost = potential_cost
                    next_hop = neighbor

            if min_cost != self.distanceVector[dst] or next_hop != self.nextHops[dst]:
                updated = True
                self.distanceVector[dst] = min_cost
                self.nextHops[dst] = next_hop

        return updated

    def propagate(self):
        for neighbor in self.neighbors:
            sendVector = deepcopy(self.distanceVector)

            if self.sim.POISONREVERSE:
                for i in range(self.sim.NUM_NODES):
                    if self.nextHops[i] == neighbor:
                        sendVector[i] = self.sim.INFINITY

            packet = RouterPacket.RouterPacket(self.myID, neighbor, sendVector)
            self.sendUpdate(packet)

    def sendUpdate(self, pkt):
        self.sim.toLayer2(pkt)

    def updateLinkCost(self, dest, newcost):
        
        oldcost = self.costs[dest]
        self.costs[dest] = newcost
        self.distanceTable[self.myID][dest] = newcost

        updated = False

        # Beräkna om mincost efter förändring av länkkostnad
        updated = self.calcMincost()

        if updated:
            self.propagate()

    def printDistanceTable(self):
      
        time_now = str(self.sim.getClocktime())
        
        self.myGUI.println(f"Current state for router {self.myID} at time {time_now}")
        

        header = f"    dst |" + "  ".join(f"{i}" for i in range(self.sim.NUM_NODES))
        
        separator_line = "-" * len(header)
        
 
        self.myGUI.println("\nDistancetable:")
        self.myGUI.println(header)
        self.myGUI.println(separator_line)

        nodes_to_print = [self.myID] + self.neighbors
        for nbr in nodes_to_print:
            row_data = "  ".join(F.format(self.distanceTable[nbr][dst], 3) for dst in range(self.sim.NUM_NODES))
            row_str = f"nbr {nbr} | {row_data}"
            self.myGUI.println(row_str)

        
       
        dv_header_line = "\ndst  |  " + "  ".join(f"{i}" for i in range(self.sim.NUM_NODES))
        
        dv_separator_line = "-" * len(dv_header_line)
        
        costs_row_str   = "cost  |  " + "  ".join(str(self.distanceVector[i]) for i in range(self.sim.NUM_NODES))
        
        routes_row_str  = "route |  " + "  ".join(str(self.nextHops[i]) if (self.nextHops[i] is not None) else "-" 
                                                  for i in range(self.sim.NUM_NODES))

        
        
        self.myGUI.println("\nOur distance vector and routes:")
        
      
        self.myGUI.println(dv_header_line)
        self.myGUI.println(dv_separator_line)
        self.myGUI.println(costs_row_str)
