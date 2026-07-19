/* Decompile a list of function addresses from the existing local project
 * into per-function C draft files (Bucket 3 workflow step "Ghidra draft").
 *
 * Output is DISC-DERIVED and goes to gitignored build/ only — drafts are
 * consulted while writing our own C, never committed (legal rules).
 *
 * Args: <addrs.txt> <outdir>
 *   addrs.txt — one hex vma per line
 *   outdir    — receives <vma>.c files
 *
 * Run via tools/ghidra_decomp.sh (opens the project with -process).
 */
import java.io.File;
import java.io.FileWriter;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.List;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class DecompileList extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        List<String> addrs = Files.readAllLines(Paths.get(args[0]));
        File outdir = new File(args[1]);
        outdir.mkdirs();

        DecompInterface ifc = new DecompInterface();
        ifc.openProgram(currentProgram);
        int ok = 0, bad = 0;
        for (String line : addrs) {
            String s = line.trim();
            if (s.isEmpty() || s.startsWith("#")) continue;
            Address a = currentProgram.getAddressFactory()
                    .getDefaultAddressSpace().getAddress(Long.decode(s));
            Function f = getFunctionAt(a);
            String name = String.format("%07x", a.getOffset());
            File out = new File(outdir, name + ".c");
            if (f == null) {
                println("DecompileList: no function at " + s);
                bad++;
                continue;
            }
            DecompileResults res = ifc.decompileFunction(f, 60, monitor);
            try (FileWriter w = new FileWriter(out)) {
                if (res.decompileCompleted()) {
                    w.write(res.getDecompiledFunction().getC());
                    ok++;
                } else {
                    w.write("/* decompile failed: " + res.getErrorMessage() + " */\n");
                    bad++;
                }
            }
        }
        ifc.dispose();
        println("DecompileList: " + ok + " ok, " + bad + " failed");
    }
}
