function test_fullmpmu_patch(patched_ks1_dir)
% Deterministic test of the field2026 fullMPMU.m patch (ephys/run_k1_block.py): the ORIGINAL accumulation
% (st3 grown by cat; cProj/cProjPC preallocated, then auto-grown past the preallocation) and the PATCHED one
% (preallocate + field2026_grow doubling + in-place fill + trim) must give identical st3, cProj and cProjPC
% for the same sequence of per-batch outputs. Small preallocations (N0) force many growth steps; the batch sizes
% include empty batches. The GPU kernels are not involved: this checks only the lines the patch changes.
%   matlab -batch "test_fullmpmu_patch('<tools>/KiloSort1_field2026')"
addpath(fullfile(patched_ks1_dir, 'mainLoop'));
rng(7);
nbatch = 3000; N0 = 1000; nNeigh = 16; nNeighPC = 16; NT = 32832; ntbuff = 64; nt0min = 20;
ops = struct('nNeigh', nNeigh, 'nNeighPC', nNeighPC, 'ntbuff', ntbuff, 'nt0min', nt0min);
sizes = randi([0 900], nbatch, 1); sizes(rand(nbatch,1) < 0.05) = 0;
% ---- original logic (fullMPMU.m lines 64-65, 79, 101, 155-194, 205-226), with preallocation N0 ----
st3 = []; rezA.cProj = zeros(N0, nNeigh, 'single'); rezA.cProjPC = zeros(N0, 3*nNeighPC, 'single'); irun = 0;
for ibatch = 1:nbatch
    [st, id, x, cpc, cp] = fake_batch(sizes(ibatch), ibatch, nNeigh, nNeighPC);
    if ~isempty(st)
        rezA.cProjPC(irun + (1:numel(st)), :) = cpc;
        rezA.cProj(irun + (1:numel(st)), :) = cp;
        irun = irun + numel(st);
        if ibatch==1, ioffset = 0; else, ioffset = ntbuff; end
        st = st - ioffset;
        STT = cat(2, nt0min + double(st) + (NT-ntbuff)*(ibatch-1), double(id)+1, double(x), ibatch*ones(numel(x),1));
        st3 = cat(1, st3, STT);
    end
end
[~, isort] = sort(st3(:,1), 'ascend'); stA = st3(isort,:);
rezA.cProjPC(irun+1:end, :) = []; rezA.cProjPC = rezA.cProjPC(isort, :);
rezA.cProj(irun+1:end, :) = [];   rezA.cProj = rezA.cProj(isort, :);
% ---- patched logic ----
st3 = zeros(N0, 4); rezB.cProj = zeros(N0, nNeigh, 'single'); rezB.cProjPC = zeros(N0, 3*nNeighPC, 'single'); irun = 0;
for ibatch = 1:nbatch
    [st, id, x, cpc, cp] = fake_batch(sizes(ibatch), ibatch, nNeigh, nNeighPC);
    if ~isempty(st)
        [st3, rezB] = field2026_grow(st3, rezB, irun, numel(st), ops);
        rezB.cProjPC(irun + (1:numel(st)), :) = cpc;
        rezB.cProj(irun + (1:numel(st)), :) = cp;
        irun = irun + numel(st);
        if ibatch==1, ioffset = 0; else, ioffset = ntbuff; end
        st = st - ioffset;
        STT = cat(2, nt0min + double(st) + (NT-ntbuff)*(ibatch-1), double(id)+1, double(x), ibatch*ones(numel(x),1));
        st3(irun - numel(st) + (1:numel(st)), :) = STT;
    end
end
st3 = st3(1:irun, :);
[~, isort] = sort(st3(:,1), 'ascend'); stB = st3(isort,:);
rezB.cProjPC(irun+1:end, :) = []; rezB.cProjPC = rezB.cProjPC(isort, :);
rezB.cProj(irun+1:end, :) = [];   rezB.cProj = rezB.cProj(isort, :);
ok = isequal(stA, stB) && isequal(rezA.cProj, rezB.cProj) && isequal(rezA.cProjPC, rezB.cProjPC) ...
     && strcmp(class(rezB.cProj), 'single') && strcmp(class(rezB.cProjPC), 'single');
fprintf('spikes %d, batches %d, growth from %d rows: st3 %s, cProj %s, cProjPC %s\n', irun, nbatch, N0, ...
    mat2str(isequal(stA, stB)), mat2str(isequal(rezA.cProj, rezB.cProj)), mat2str(isequal(rezA.cProjPC, rezB.cProjPC)));
if ok, fprintf('TEST PASS\n'); else, error('TEST FAIL: patched accumulation differs from the original'); end
end

function [st, id, x, cpc, cp] = fake_batch(n, ibatch, nNeigh, nNeighPC)
% deterministic per batch, so both passes see the same data
s = RandStream('mt19937ar', 'Seed', ibatch);
st = int32(sort(randi(s, [1 32768], n, 1)));
id = int32(randi(s, [0 511], n, 1));
x = single(rand(s, n, 1) * 50);
cpc = single(randn(s, n, 3*nNeighPC));
cp = single(randn(s, n, nNeigh));
end
