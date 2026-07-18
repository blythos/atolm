/* Bucket 2 Ghidra post-script: seed function starts from our prologue
 * detector (FINDINGS gotcha: never trust default boundary detection —
 * multiple-return functions get mis-split and literal pools decode as fake
 * instructions), run auto-analysis, apply the committed symbols file, then
 * export functions + instruction coverage + xref counts as JSON for
 * tools/ghidra_reconcile.py.
 *
 * Args: <seeds.txt> <out.json> [symbols.sym]
 *   seeds.txt — one hex address per line (from tools/sh2_map.py)
 *   symbols.sym — "0xADDR name provenance" lines (config/symbols/)
 *
 * Run by tools/ghidra_gen.sh with -noanalysis on import; analysis happens
 * here, after seeding, so seeds win over Ghidra's guesses.
 */
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSpace;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.SourceType;

import java.io.BufferedReader;
import java.io.FileReader;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.List;

public class SeedAndExport extends GhidraScript {

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String seedPath = args[0];
        String outPath = args[1];
        String symPath = args.length > 2 ? args[2] : null;

        AddressSpace space =
            currentProgram.getAddressFactory().getDefaultAddressSpace();

        // 1. seed: disassemble + create a function at every detector start
        int seeded = 0, failed = 0;
        try (BufferedReader r = new BufferedReader(new FileReader(seedPath))) {
            String line;
            while ((line = r.readLine()) != null) {
                line = line.trim();
                if (line.isEmpty()) continue;
                Address a = space.getAddress(Long.decode(line));
                disassemble(a);
                if (createFunction(a, null) != null) seeded++;
                else failed++;
            }
        }
        println("seeded " + seeded + " functions (" + failed
                + " rejected by Ghidra)");

        // 2. full auto-analysis on top of the seeds
        analyzeAll(currentProgram);

        // 3. apply committed symbol names (provenance lives in the .sym
        //    file and the manifest; Ghidra just gets the name)
        int named = 0;
        if (symPath != null && new java.io.File(symPath).exists()) {
            try (BufferedReader r =
                     new BufferedReader(new FileReader(symPath))) {
                String line;
                while ((line = r.readLine()) != null) {
                    line = line.trim();
                    if (line.isEmpty() || line.startsWith("#")) continue;
                    String[] tok = line.split("\\s+");
                    Address a = space.getAddress(Long.decode(tok[0]));
                    Function f = getFunctionAt(a);
                    if (f != null) {
                        f.setName(tok[1], SourceType.IMPORTED);
                    } else {
                        createLabel(a, tok[1], true, SourceType.IMPORTED);
                    }
                    named++;
                }
            }
            println("applied " + named + " symbols");
        }

        // 4. export
        try (PrintWriter w = new PrintWriter(outPath)) {
            w.println("{");
            w.println("\"functions\": [");
            FunctionIterator it =
                currentProgram.getFunctionManager().getFunctions(true);
            boolean first = true;
            while (it.hasNext()) {
                Function f = it.next();
                long entry = f.getEntryPoint().getOffset();
                long size = f.getBody().getNumAddresses();
                int callers = 0;
                ReferenceIterator ri = currentProgram.getReferenceManager()
                        .getReferencesTo(f.getEntryPoint());
                while (ri.hasNext()) {
                    Reference ref = ri.next();
                    if (ref.getReferenceType().isCall()) callers++;
                }
                if (!first) w.println(",");
                first = false;
                w.print("{\"entry\": " + entry + ", \"size\": " + size
                        + ", \"callers\": " + callers + ", \"name\": \""
                        + f.getName() + "\"}");
            }
            w.println("\n],");

            // contiguous instruction coverage ranges
            w.println("\"instr_ranges\": [");
            InstructionIterator ii =
                currentProgram.getListing().getInstructions(true);
            long rs = -1, re = -1;
            List<String> ranges = new ArrayList<>();
            while (ii.hasNext()) {
                Instruction ins = ii.next();
                long a = ins.getAddress().getOffset();
                long e = ins.getMaxAddress().getOffset() + 1;
                if (rs < 0) { rs = a; re = e; }
                else if (a == re) { re = e; }
                else { ranges.add("[" + rs + ", " + re + "]"); rs = a; re = e; }
            }
            if (rs >= 0) ranges.add("[" + rs + ", " + re + "]");
            w.println(String.join(",\n", ranges));
            w.println("],");

            // defined data (merged by contiguity)
            w.println("\"data_ranges\": [");
            DataIterator di =
                currentProgram.getListing().getDefinedData(true);
            rs = -1; re = -1;
            ranges = new ArrayList<>();
            while (di.hasNext()) {
                Data d = di.next();
                long a = d.getAddress().getOffset();
                long e = d.getMaxAddress().getOffset() + 1;
                if (rs < 0) { rs = a; re = e; }
                else if (a == re) { re = e; }
                else { ranges.add("[" + rs + ", " + re + "]"); rs = a; re = e; }
            }
            if (rs >= 0) ranges.add("[" + rs + ", " + re + "]");
            w.println(String.join(",\n", ranges));
            w.println("]");
            w.println("}");
        }
        println("exported to " + outPath);
    }
}
