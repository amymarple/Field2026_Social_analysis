function ds_batch(listfile, outdir, dsroot, nets, settings)
% Headless DeepSqueak detection on a list of WAVs (cohort-3 in-house mics). Read-only on the audio; the DeepSqueak
% checkout is only put on the path (never edited). Per WAV, writes into outdir:
%   <stem>.mat  - the DeepSqueak detection file (Calls, detection_metadata, audiodata; -v7.3), as the GUI's
%                 multinetdect_Callback saves it, so the file opens in the DeepSqueak GUI for manual review / labels;
%   <stem>.csv  - one row per call: begin_s, dur_s, low_kHz, high_kHz, score, type, accept (from Calls.Box etc.);
%   timing.csv  - (appended) file, network, seconds analysed, boxes, elapsed s.
% listfile: text file with one WAV path per line. nets: cell array of file names in <dsroot>/Networks.
% settings: one column per network = [length_s (0 = whole file); high_kHz; low_kHz; score_threshold].
%
% Example (repo plan implementation_plan/2026-10-08-mic-imu-sync.md, USV line):
%   matlab -batch "addpath('ephys/usv'); ds_batch('list.txt','D:/out','D:/Documents/GitHub/WILD_frank/DeepSqueak', ...
%       {'2025.02.04.Rat.YoloR2.mat','2025.02.05.Rat.Long.YoloR2.mat'}, [300 300; 100 35; 30 18; 0 0])"
addpath(genpath(dsroot));
if ~exist(outdir, 'dir'); mkdir(outdir); end
wavs = strtrim(splitlines(fileread(listfile)));
wavs = wavs(~cellfun('isempty', wavs));
tf = fopen(fullfile(outdir, 'timing.csv'), 'a');
for j = 1:numel(wavs)
    wav = wavs{j};
    [~, stem] = fileparts(wav);
    Calls = [];
    for k = 1:numel(nets)
        NN = load(fullfile(dsroot, 'Networks', nets{k}));
        t0 = tic;
        C = SqueakDetect(wav, NN, [stem '.wav'], settings(:, k), j, numel(wavs), nets{k});
        el = toc(t0);
        fprintf(1, '%s  %s: %d boxes, %.1f s\n', stem, nets{k}, height(C), el);
        fprintf(tf, '%s,%s,%g,%d,%.1f\n', stem, nets{k}, settings(1, k), height(C), el);
        Calls = [Calls; C]; %#ok<AGROW>
    end
    if isempty(Calls)
        fprintf(1, 'no calls: %s\n', stem);
        continue
    end
    Calls = Automerge_Callback(Calls, [], wav);
    detection_metadata = struct('Settings', settings, 'detectiontime', datestr(datetime('now'), 'yyyy-mm-dd HH_MM PM'), ...
        'networkselections', {nets});
    audiodata = audioinfo(wav);
    save(fullfile(outdir, [stem '.mat']), 'Calls', 'detection_metadata', 'audiodata', '-v7.3', '-mat');
    B = Calls.Box;                       % [begin_s, low_kHz, dur_s, bandwidth_kHz]
    T = table(B(:, 1), B(:, 3), B(:, 2), B(:, 2) + B(:, 4), Calls.Score, string(Calls.Type), Calls.Accept, ...
        'VariableNames', {'begin_s', 'dur_s', 'low_kHz', 'high_kHz', 'score', 'type', 'accept'});
    writetable(T, fullfile(outdir, [stem '.csv']));
end
fclose(tf);
end
