function test_zerooutkcoords_patch(original_ks1_dir, patched_ks1_dir)
% zeroOutKcoords with an all-dead channel group (kcoords of the connected channels = 2,3,4; group 1 empty, as for
% SF10 whose shank 1 is dead): the ORIGINAL gives NaN nEffective and confines no template; the PATCHED confines every
% template except the single most-spread one (criterionNoiseChannels 1e-5), and is identical to the original when no
% group is empty.
%   matlab -batch "test_zerooutkcoords_patch('<pipeline>/sorter/KiloSort1', '<tools>/KiloSort1_field2026')"
rng(3); Nchan = 45; Nfilt = 64; Nrank = 3;
k_dead = [2*ones(15,1); 3*ones(14,1); 4*ones(16,1)];        % group 1 has no connected channel
k_full = [1*ones(11,1); 2*ones(12,1); 3*ones(11,1); 4*ones(11,1)];
U = randn(Nchan, Nfilt, Nrank, 'single');
orig = run_in(original_ks1_dir, U, k_dead); patched = run_in(patched_ks1_dir, U, k_dead);
spans = @(V, k) arrayfun(@(i) numel(unique(k(any(abs(V(:,i,:)) > 0, 3)))), 1:size(V,2));
so = spans(orig, k_dead); sp = spans(patched, k_dead);
fprintf('dead group: templates spanning >1 group: original %d / patched %d of %d\n', sum(so > 1), sum(sp > 1), Nfilt);
same_full = isequal(run_in(original_ks1_dir, U, k_full), run_in(patched_ks1_dir, U, k_full));
fprintf('no empty group: original == patched: %d\n', same_full);
if sum(so > 1) > 1 && sum(sp > 1) <= 1 && same_full, fprintf('TEST PASS\n'); else, error('TEST FAIL'); end
end

function V = run_in(d, U, k)
old = pwd; c = onCleanup(@() cd(old)); cd(fullfile(d, 'mainLoop'));
V = zeroOutKcoords(U, k, 1e-5);
end
